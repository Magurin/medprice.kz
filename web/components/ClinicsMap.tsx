"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap, LayerGroup, Marker } from "leaflet";
import "leaflet/dist/leaflet.css";
import { ClinicRow, twoGisRoute } from "@/lib/api";

// Центр Казахстана — стартовый вид, пока не подгрузились клиники.
const KZ_CENTER: [number, number] = [48.0, 67.0];

type Props = {
  clinics: ClinicRow[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
};

// Маркер-«пин» через divIcon: не зависит от картинок Leaflet (которые ломает бандлер).
function pinHtml(active: boolean) {
  const fill = active ? "#0f766e" : "#0d9488";
  return `<div style="transform:translate(-50%,-100%)">
    <svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.2 13 21 13 21s13-11.8 13-21C26 5.8 20.2 0 13 0z" fill="${fill}"/>
      <circle cx="13" cy="13" r="5" fill="#fff"/>
    </svg>
  </div>`;
}

// Содержимое попапа: название, адрес, рейтинг 2ГИС, ссылки на отзывы и маршрут.
function popupHtml(c: ClinicRow): string {
  const esc = (s: string) =>
    s.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]!));
  const addr = c.address
    ? `<div style="color:#64748b;font-size:12px;margin-top:2px">${esc(c.address)}</div>`
    : "";
  const rating =
    c.rating != null
      ? `<div style="margin-top:4px;font-size:12px;color:#0f172a">` +
        `<span style="color:#f59e0b">★</span> ${c.rating.toFixed(1)}` +
        (c.reviews_count ? ` <span style="color:#94a3b8">(${c.reviews_count})</span>` : "") +
        `</div>`
      : "";
  const reviews = c.twogis_url
    ? `<a href="${c.twogis_url}" target="_blank" rel="noopener" style="color:#19aa1e;font-size:12px;text-decoration:none">Отзывы в 2ГИС →</a>`
    : "";
  const route = twoGisRoute(c.lat, c.lng);
  const routeBtn = route
    ? `<a href="${route}" target="_blank" rel="noopener" style="display:inline-block;padding:4px 10px;border-radius:8px;background:#0d9488;color:#fff;font-size:12px;text-decoration:none">🚗 Маршрут</a>`
    : "";
  return (
    `<div style="min-width:180px;max-width:260px;font-family:inherit;line-height:1.3">` +
    `<div style="font-weight:600;color:#0f172a;font-size:13px">${esc(c.name)}</div>` +
    addr +
    rating +
    `<div style="margin-top:6px;display:flex;flex-direction:column;gap:4px;align-items:flex-start">${reviews}${routeBtn}</div>` +
    `</div>`
  );
}

export default function ClinicsMap({ clinics, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const layerRef = useRef<LayerGroup | null>(null);
  const markersRef = useRef<Map<number, Marker>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Инициализация карты один раз.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    let cancelled = false;
    (async () => {
      const L = await import("leaflet");
      if (cancelled || !containerRef.current) return;
      const map = L.map(containerRef.current, {
        center: KZ_CENTER,
        zoom: 5,
        scrollWheelZoom: true,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
      // На случай если контейнер появился после ресайза/таба.
      setTimeout(() => map.invalidateSize(), 0);
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
      markersRef.current.clear();
    };
  }, []);

  // Перерисовка маркеров при смене списка. fitBounds — только здесь (не на выборе).
  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    let cancelled = false;
    (async () => {
      const L = await import("leaflet");
      if (cancelled) return;
      layer.clearLayers();
      markersRef.current.clear();
      const pts = clinics.filter((c) => c.lat != null && c.lng != null);
      const bounds: [number, number][] = [];
      for (const c of pts) {
        const ll: [number, number] = [c.lat as number, c.lng as number];
        bounds.push(ll);
        const marker = L.marker(ll, {
          icon: L.divIcon({
            html: pinHtml(c.id === selectedId),
            className: "",
            iconSize: [26, 34],
            iconAnchor: [13, 34],
          }),
        });
        marker.bindPopup(popupHtml(c), { offset: [0, -28] });
        marker.on("click", () => onSelectRef.current?.(c.id));
        marker.addTo(layer);
        markersRef.current.set(c.id, marker);
      }
      if (bounds.length === 1) {
        map.setView(bounds[0], 13);
      } else if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [40, 40] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clinics]);

  // Выбор клиники (из списка или клика по пину): центрируем и открываем попап.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || selectedId == null) return;
    const c = clinics.find((x) => x.id === selectedId);
    if (c?.lat == null || c?.lng == null) return;
    map.setView([c.lat, c.lng], Math.max(map.getZoom(), 13), { animate: true });
    markersRef.current.get(selectedId)?.openPopup();
  }, [selectedId, clinics]);

  return <div ref={containerRef} className="h-full w-full" />;
}
