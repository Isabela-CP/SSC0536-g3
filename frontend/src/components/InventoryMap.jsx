import React, { useEffect, useRef, useState } from 'react'
import { hasCoordinates } from '../domain/reading.js'
import 'leaflet/dist/leaflet.css'
export default function InventoryMap({ items, title = 'Mapa da cidade' }) {
  const container = useRef(null)
  const [error, setError] = useState('')
  const located = items.filter(hasCoordinates)
  useEffect(() => {
    if (!located.length) return
    let active = true,
      map,
      observer
    setError('')
    import('leaflet')
      .then((module) => {
        if (!active) return
        const L = module.default || module
        map = L.map(container.current, { scrollWheelZoom: false, zoomControl: false })
        L.control
          .zoom({ position: 'bottomright', zoomInTitle: 'Aproximar', zoomOutTitle: 'Afastar' })
          .addTo(map)
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        })
          .on(
            'tileerror',
            () =>
              active &&
              setError(
                'O mapa de ruas não pôde ser carregado. As coordenadas continuam disponíveis abaixo.',
              ),
          )
          .addTo(map)
        const bounds = []
        for (const item of located) {
          const point = [item.latitude, item.longitude]
          bounds.push(point)
          const link = document.createElement('a')
          link.textContent = item.nome_fantasia
          link.href = `#/estabelecimentos/${encodeURIComponent(item.id_estabelecimento)}`
          L.circleMarker(point, {
            radius: 7,
            color: '#e56d28',
            fillColor: '#e56d28',
            fillOpacity: 0.85,
          })
            .bindPopup(link)
            .addTo(map)
        }
        map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 })
        observer = new ResizeObserver(() => map.invalidateSize())
        observer.observe(container.current)
      })
      .catch(() => active && setError('Não foi possível iniciar o mapa.'))
    return () => {
      active = false
      observer?.disconnect()
      map?.remove()
    }
  }, [items])
  return (
    <section className="inventory-map-card" aria-label={title}>
      <h2 className="map-title">{title}</h2>
      {located.length ? (
        <div
          className="inventory-map"
          ref={container}
          role="region"
          aria-label="Mapa interativo das hospedagens"
        />
      ) : (
        <p className="map-empty">Nenhuma hospedagem com coordenadas válidas.</p>
      )}
      {error && (
        <p role="status" className="muted">
          {error}
        </p>
      )}
      {items.length !== located.length && (
        <p className="map-note">
          {items.length - located.length} hospedagem(ns) sem coordenadas válidas.
        </p>
      )}
      {!!located.length && (
        <details className="map-coordinates">
          <summary>Ver localizações ({located.length})</summary>
          <ul>
            {located.map((item) => (
              <li key={item.id_estabelecimento}>
                <a href={`#/estabelecimentos/${item.id_estabelecimento}`}>
                  {item.nome_fantasia}
                </a>
                : {item.latitude}, {item.longitude}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
