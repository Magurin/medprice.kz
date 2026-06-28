"use client";

import { useEffect, useRef } from "react";
import { ClinicRow, twoGisRoute } from "@/lib/api";

// Ключ Map Tiles API (MapGL). Боевой задаётся через env в Vercel
// (NEXT_PUBLIC_2GIS_MAPGL_KEY); дефолт — публичный ДЕМО-ключ 2ГИС, только для
// разработки (залимичен, в прод не годится).
const MAPGL_KEY =
  process.env.NEXT_PUBLIC_2GIS_MAPGL_KEY || "42d017f1-1c19-4d3c-a25a-2c97b8e3c8e8";

// Центр Казахстана. ВНИМАНИЕ: MapGL принимает координаты как [долгота, широта].
const KZ_CENTER: [number, number] = [67.0, 48.0];

type Props = {
  clinics: ClinicRow[];
  selectedId?: number | null;
  onSelect?: (id: number) => void;
};

// Пин как data-URI (не зависит от ассетов бандлера).
function pinIcon(): string {
  const svg =
    `<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg">` +
    `<path d="M13 0C5.8 0 0 5.8 0 13c0 9.2 13 21 13 21s13-11.8 13-21C26 5.8 20.2 0 13 0z" fill="#0d9488"/>` +
    `<circle cx="13" cy="13" r="5" fill="#fff"/></svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

// Однократная загрузка скрипта MapGL; результат — глобал window.mapgl.
let mapglPromise: Promise<unknown> | null = null;
function loadMapgl(): Promise<any> {
  const w = window as any;
  if (w.mapgl) return Promise.resolve(w.mapgl);
  if (!mapglPromise) {
    mapglPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://mapgl.2gis.com/api/js/v1";
      s.async = true;
      s.onload = () => resolve((window as any).mapgl);
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  return mapglPromise as Promise<any>;
}

// Содержимое попапа. transform поднимает его над пином и центрирует по горизонтали.
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
    ? `<a href="${route}" target="_blank" rel="noopener" style="display:inline-block;margin-top:2px;padding:4px 10px;border-radius:8px;background:#0d9488;color:#fff;font-size:12px;text-decoration:none">🚗 Маршрут</a>`
    : "";
  return (
    `<div style="transform:translate(-50%,calc(-100% - 38px));min-width:190px;max-width:260px;` +
    `background:#fff;border-radius:12px;padding:10px 12px;` +
    `box-shadow:0 12px 30px -10px rgba(12,24,34,.45);font-family:inherit;line-height:1.3">` +
    `<div style="font-weight:600;color:#0f172a;font-size:13px">${esc(c.name)}</div>` +
    addr +
    rating +
    `<div style="margin-top:6px;display:flex;flex-direction:column;gap:4px;align-items:flex-start">${reviews}${routeBtn}</div>` +
    `</div>`
  );
}

export default function ClinicsMap({ clinics, selectedId, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const popupRef = useRef<any>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const closePopup = () => {
    popupRef.current?.destroy();
    popupRef.current = null;
  };

  // Инициализация карты один раз.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    let cancelled = false;
    loadMapgl()
      .then((mapgl) => {
        if (cancelled || !containerRef.current || mapRef.current) return;
        const map = new mapgl.Map(containerRef.current, {
          center: KZ_CENTER,
          zoom: 4.4,
          key: MAPGL_KEY,
        });
        map.on("click", closePopup);
        mapRef.current = map;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      closePopup();
      markersRef.current.forEach((m) => m.destroy());
      markersRef.current = [];
      mapRef.current?.destroy();
      mapRef.current = null;
    };
  }, []);

  // Маркеры при смене списка клиник. fitBounds — только здесь (не на выборе).
  useEffect(() => {
    const map = mapRef.current;
    const mapgl = (window as any).mapgl;
    if (!map || !mapgl) return;
    markersRef.current.forEach((m) => m.destroy());
    markersRef.current = [];
    const pts = clinics.filter((c) => c.lat != null && c.lng != null);
    const icon = pinIcon();
    for (const c of pts) {
      const marker = new mapgl.Marker(map, {
        coordinates: [c.lng as number, c.lat as number],
        icon,
        anchor: [13, 34],
        size: [26, 34],
      });
      marker.on("click", () => onSelectRef.current?.(c.id));
      markersRef.current.push(marker);
    }
    if (pts.length === 1) {
      map.setCenter([pts[0].lng as number, pts[0].lat as number]);
      map.setZoom(13);
    } else if (pts.length > 1) {
      const lngs = pts.map((p) => p.lng as number);
      const lats = pts.map((p) => p.lat as number);
      map.fitBounds(
        {
          northEast: [Math.max(...lngs), Math.max(...lats)],
          southWest: [Math.min(...lngs), Math.min(...lats)],
        },
        { padding: { top: 50, bottom: 50, left: 50, right: 50 } }
      );
    }
  }, [clinics]);

  // Выбор клиники (из списка или клика по пину): центрируем и открываем попап.
  useEffect(() => {
    const map = mapRef.current;
    const mapgl = (window as any).mapgl;
    if (!map || !mapgl || selectedId == null) return;
    const c = clinics.find((x) => x.id === selectedId);
    if (c?.lat == null || c?.lng == null) return;
    map.setCenter([c.lng, c.lat]);
    if ((map.getZoom?.() ?? 0) < 13) map.setZoom(13);
    closePopup();
    popupRef.current = new mapgl.HtmlMarker(map, {
      coordinates: [c.lng, c.lat],
      html: popupHtml(c),
    });
  }, [selectedId, clinics]);

  return <div ref={containerRef} className="h-full w-full" />;
}
