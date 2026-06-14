import React from 'react';
import { MapContainer, ImageOverlay, Marker, Popup, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const redIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const robotIcon = new L.divIcon({
  className: 'fluid-robot-marker',
  html: `<div style="width: 16px; height: 16px; background-color: #3b82f6; border: 3px solid white; border-radius: 50%; box-shadow: 0 0 6px rgba(59,130,246,0.8);"></div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11]
});

export const MAP_BOUNDS = [[0, -1250], [2400, 2750]];

export default function MapPanel({ markers = [], robotPos = { x: 0, y: 2 }, onResolve, mapRef }) {
  const imageUrl = '/kat-plani-dikey.svg';

  return (
    <MapContainer
      ref={mapRef}
      crs={L.CRS.Simple}
      bounds={MAP_BOUNDS}
      zoomSnap={0.1}
      minZoom={-4}
      maxZoom={2}
      style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: '100%', backgroundColor: '#e2e8f0' }}
    >
      <style>
        {`
          .fluid-robot-marker {
            transition: transform 0.2s linear !important;
          }
        `}
      </style>
      <ImageOverlay url={imageUrl} bounds={MAP_BOUNDS} opacity={1} />

      {/* Robot Konumu */}
      {/* Koridor SVG'de x=500 hizasında. İleri doğru gidiş Leaflet y eksenine denk gelir (robotPos.x * 100). */}
      <Marker position={[robotPos.x * 100, 500]} icon={robotIcon}>
        <Popup><b>Robot Konumu</b><br />İleri: {robotPos.x.toFixed(2)}m</Popup>
      </Marker>

      {/* İhlal Pinleri */}
      {markers.map((marker, index) => (
        <Marker key={index} position={[marker.x * 100, 500]} icon={redIcon}>
          <Popup>
            <strong style={{ color: '#dc2626' }}>🚨 İHLAL: {marker.type}</strong><br />
            {marker.time}
            <div style={{ marginTop: '10px' }}>
              <button
                onClick={() => onResolve(index)}
                style={{ width: '100%', padding: '6px', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
              >
                ✅ Sorun Giderildi
              </button>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}