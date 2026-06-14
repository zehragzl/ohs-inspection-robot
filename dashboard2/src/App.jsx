import React, { useState, useEffect, useRef } from 'react'
import mqtt from 'mqtt'
import { MQTT_CONFIG, TOPICS } from './config'
import MapPanel, { MAP_BOUNDS } from './MapPanel'
import { collection, addDoc } from 'firebase/firestore'
import { db } from './firebase'
import LogViewerModal from './LogViewerModal'

const PPE_LABELS = {
  'no_helmet':  'Baret Yok',
  'no_vest':    'Yelek Yok',
  'no_goggles': 'Gözlük Yok',
}

const getFormattedDateTime = () => {
  return new Date().toLocaleString('tr-TR', { 
    year: 'numeric', month: '2-digit', day: '2-digit', 
    hour: '2-digit', minute: '2-digit', second: '2-digit' 
  });
}

export default function App() {
  const [activeAlert, setActiveAlert]   = useState(null)
  const [events, setEvents]             = useState([{ id: 1, type: 'INFO', time: getFormattedDateTime(), text: 'Sistem başlatıldı. Pi bağlantısı bekleniyor...' }])
  const [sensorData, setSensorData]     = useState({ temp: 0, gas: 0, noise: 0 })
  const [envData, setEnvData]           = useState(null)
  const [logFilter, setLogFilter]       = useState('ALL')
  const [hazardActive, setHazardActive] = useState(false)
  const [isLogModalOpen, setIsLogModalOpen] = useState(false)
  const [isCameraOpen, setIsCameraOpen]     = useState(false)
  
  // DÜZELTİLDİ: Robot 10 metrelik geniş haritanın tam ortasında (X: 5) ve 0. metrede (Y: 0) başlar.
  const [robotPos, setRobotPos]         = useState({ x: 0, y: 2 })
  const [navData, setNavData]           = useState(null)
  const [mapMarkers, setMapMarkers]     = useState([])
  const [isMoving, setIsMoving]         = useState(false)
  const [connected, setConnected]       = useState(false)
  const [connecting, setConnecting]     = useState(false)

  const mqttClientRef = useRef(null)
  const robotPosRef   = useRef({ x: 0, y: 2 })
  const mapRef        = useRef(null)

  const resetMap = () => {
    if (mapRef.current) {
      mapRef.current.fitBounds(MAP_BOUNDS, { animate: true, duration: 0.5 })
    }
    setMapMarkers([])
    setRobotPos({ x: 0, y: 2 })
    setNavData(null)
  }

  const addEvent = async (type, text) => {
    const newEvent = {
      id: Date.now() + Math.random(),
      type,
      time: getFormattedDateTime(),
      text,
    }
    setEvents(prev => [newEvent, ...prev].slice(0, 15))

    try {
      if (db) {
        await addDoc(collection(db, "events"), {
          type: newEvent.type,
          time: newEvent.time,
          text: newEvent.text,
          timestamp: new Date().toISOString()
        })
      }
    } catch (e) {
      console.error("Firestore event kaydı hatası: ", e)
    }
  }

  useEffect(() => {
    robotPosRef.current = robotPos
  }, [robotPos])

  useEffect(() => {
    const brokerUrl = `ws://${MQTT_CONFIG.PI_IP}:${MQTT_CONFIG.PI_MQTT_WS_PORT}`
    setConnecting(true)

    const client = mqtt.connect(brokerUrl, {
      clientId: `ohs_dashboard_${Math.random().toString(16).slice(2, 10)}`,
      clean: true,
      reconnectPeriod: MQTT_CONFIG.RECONNECT_PERIOD,
      connectTimeout: MQTT_CONFIG.CONNECT_TIMEOUT,
    })

    client.on('connect', () => {
      setConnected(true)
      setConnecting(false)
      addEvent('CLEAN', '✅ Raspberry Pi bağlantısı kuruldu')
      client.subscribe([
        TOPICS.PPE_VIOLATION,
        TOPICS.ENV_HAZARD,
        TOPICS.NAV_POSITION,
        TOPICS.NAV_WAYPOINT,
        TOPICS.ROBOT_FEEDBACK,
      ])
    })

    client.on('disconnect', () => {
      setConnected(false)
      addEvent('CRITICAL', '❌ Raspberry Pi bağlantısı kesildi')
    })

    client.on('reconnect', () => {
      setConnecting(true)
      setConnected(false)
    })

    client.on('error', (err) => {
      setConnecting(false)
      addEvent('CRITICAL', `MQTT Hata: ${err.message}`)
    })

    client.on('message', (topic, message) => {
      let payload
      try { payload = JSON.parse(message.toString()) }
      catch { return }

      if (topic === TOPICS.PPE_VIOLATION) {
        const label = PPE_LABELS[payload.class] || payload.class
        const conf  = Math.round(payload.confidence * 100)

        addEvent('CRITICAL', `🦺 PPE İHLALİ: ${label} — güven: %${conf}`)
        setActiveAlert(`PPE İHLALİ: ${label}`)
        setTimeout(() => setActiveAlert(null), 4000)

        const pos = robotPosRef.current
        setMapMarkers(prev => [...prev, {
          x:    pos.x,
          y:    pos.y,
          type: label,
          time: getFormattedDateTime(),
        }].slice(-256))

        try {
          if (db) {
            addDoc(collection(db, "violations"), {
              label: label,
              confidence: conf,
              x: pos.x,
              y: pos.y,
              timestamp: new Date().toISOString()
            })
          }
        } catch (e) {
          console.error("Firestore violation kaydı hatası: ", e)
        }
      }

      else if (topic === TOPICS.ENV_HAZARD) {
        setEnvData(payload)
        setSensorData(prev => ({
          temp:  payload.metric === 'temperature' ? payload.value : prev.temp,
          gas:   payload.metric === 'gas_ppm'     ? payload.value : prev.gas,
          noise: payload.metric === 'noise_db'    ? payload.value : prev.noise,
        }))

        if (payload.hazard) {
          setHazardActive(true)
          addEvent('CRITICAL', `⚠️ TEHLİKE: ${payload.metric} = ${payload.value} ${payload.unit}`)
          setActiveAlert(`TEHLİKE: ${payload.metric} = ${payload.value} ${payload.unit}`)
          setTimeout(() => setActiveAlert(null), 4000)

          try {
            if (db) {
              addDoc(collection(db, "hazards"), {
                metric: payload.metric,
                value: payload.value,
                unit: payload.unit,
                timestamp: new Date().toISOString()
              })
            }
          } catch (e) {
            console.error("Firestore hazard kaydı hatası: ", e)
          }
        } else {
          setHazardActive(false)
        }
      }

      else if (topic === TOPICS.NAV_POSITION) {
        // DÜZELTİLDİ: Gerçek metre verisi Leaflet'e doğrudan aktarılıyor.
        const newPos = {
          x: payload.x_m, // Robot yatayda koridorun tam ortasından ilerler
          y: 2, // İleri doğru gittiği metre
        }
        setRobotPos(newPos)
        robotPosRef.current = newPos
        setNavData(payload)
        setIsMoving(payload.state === 'MOVING')

        addEvent('INFO', `📍 Waypoint #${payload.waypoint_id} — (${payload.x_m}m) — ${payload.state}`)

        if (payload.obstacle_cm < 30) {
          addEvent('CRITICAL', `🚧 Engel algılandı! Mesafe: ${payload.obstacle_cm} cm`)
        }
      }

      else if (topic === TOPICS.ROBOT_FEEDBACK) {
        if (payload.status === 'OK') {
          addEvent('CLEAN', `✅ Komut onaylandı: ${payload.detail}`)
        } else {
          addEvent('CRITICAL', `❌ Komut hatası: ${payload.detail}`)
        }
      }

      else if (topic === TOPICS.NAV_WAYPOINT) {
        addEvent('INFO', `🎯 Sonraki hedef: Waypoint #${payload.waypoint_id} — İleri: ${payload.x_m}m`)
      }
    })

    mqttClientRef.current = client
    return () => client.end(true)
  }, [])

  const sendCommand = async (commandType) => {
    if (!mqttClientRef.current?.connected) {
      addEvent('CRITICAL', '❌ HATA: Raspberry Pi bağlantısı yok, komut gönderilemedi!')
      return
    }
    if (commandType === 'START') setIsMoving(true)
    if (commandType === 'STOP')  setIsMoving(false)

    addEvent('INFO', `📡 Komut gönderiliyor: ${commandType} (SSH & MQTT)`)

    // 1. MQTT Komutu
    mqttClientRef.current.publish(
      TOPICS.ROBOT_COMMAND,
      JSON.stringify({
        cmd:           commandType,
        correlationId: `dash-${Date.now()}`,
        issuedBy:      'dashboard',
        timestamp:     new Date().toISOString(),
      })
    )

    // 2. SSH Backend Komutu
    try {
      const endpoint = commandType === 'START' ? '/api/start' : commandType === 'STOP' ? '/api/stop' : null;
      if (endpoint) {
        const response = await fetch(`http://localhost:3001${endpoint}`);
        const data = await response.json();
        
        if (data.success) {
           addEvent('CLEAN', `✅ SSH Başarılı: ${data.message}`);
        } else {
           addEvent('CRITICAL', `❌ SSH Hatası: ${data.error}`);
        }
      }
    } catch (err) {
      console.error("Backend sunucusuna bağlanılamadı:", err);
      addEvent('CRITICAL', `❌ SSH Sunucusuna ulaşılamadı. 'node server.js' çalışıyor mu?`);
    }
  }

  const handleResolveMarker = (indexToRemove) => {
    setMapMarkers(prev => prev.filter((_, i) => i !== indexToRemove))
    addEvent('CLEAN', 'Bir ihlal operatör tarafından temizlendi.')
  }

  const sensorBorder = (metric, defaultColor) =>
    hazardActive && envData?.metric === metric ? '#ef4444' : defaultColor

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#f1f5f9', fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif' }}>

      <header style={{ backgroundColor: '#1e293b', padding: '15px 25px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.2)' }}>
        <h2 style={{ margin: 0, fontSize: '20px', letterSpacing: '1px', color: '#ffffff' }}>
          Vision and Sensor-Based Autonomous OHS Inspection
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            backgroundColor: connected ? '#10b981' : connecting ? '#f59e0b' : '#ef4444',
          }} />
          <span style={{ fontSize: '13px', color: '#cbd5e1' }}>
            {connected ? '🟢 Pi Bağlı' : connecting ? '🟡 Bağlanıyor...' : '🔴 Bağlantı Yok'}
          </span>
        </div>
      </header>

      <div style={{ display: 'flex', flex: 1, padding: '15px', gap: '15px', overflow: 'hidden' }}>

        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', backgroundColor: 'white', borderRadius: '10px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)', overflow: 'hidden', position: 'relative', border: '1px solid #e2e8f0' }}>
          <div style={{ padding: '12px 20px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontWeight: 'bold', color: '#1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>📍 Canlı Kat Planı ve Robot Takibi</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
              <span style={{ color: isMoving ? '#10b981' : '#64748b' }}>
                Durum: {navData ? navData.state : (isMoving ? 'MOVING' : 'DWELLING')}
              </span>
              <button 
                onClick={() => setIsLogModalOpen(true)}
                style={{ 
                  padding: '6px 12px', 
                  backgroundColor: '#3b82f6', 
                  color: 'white',
                  border: 'none', 
                  borderRadius: '6px', 
                  cursor: 'pointer', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px', 
                  fontSize: '13px',
                  fontWeight: 'bold',
                  boxShadow: '0 1px 2px rgba(59,130,246,0.4)',
                  transition: 'all 0.2s'
                }}
              >
                <span>☁️</span> Bulut Logları
              </button>
              <button 
                onClick={() => setIsCameraOpen(!isCameraOpen)} 
                style={{ 
                  padding: '6px 12px', 
                  backgroundColor: isCameraOpen ? '#ef4444' : '#8b5cf6', 
                  color: 'white',
                  border: 'none', 
                  borderRadius: '6px', 
                  cursor: 'pointer', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px', 
                  fontSize: '13px',
                  fontWeight: 'bold',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
                  transition: 'all 0.2s'
                }}
              >
                <span>📷</span> {isCameraOpen ? 'Kamerayı Kapat' : 'Kamerayı Aç'}
              </button>
              <button 
                onClick={resetMap} 
                style={{ 
                  padding: '6px 12px', 
                  backgroundColor: '#ffffff', 
                  color: '#334155',
                  border: '1px solid #cbd5e1', 
                  borderRadius: '6px', 
                  cursor: 'pointer', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '6px', 
                  fontSize: '13px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                  transition: 'all 0.2s'
                }}
                onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#f8fafc'}
                onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#ffffff'}
              >
                <span>🎯</span> Haritayı Sıfırla
              </button>
            </div>
          </div>

          <div style={{ flex: 1, position: 'relative' }}>
            <MapPanel robotPos={robotPos} markers={mapMarkers} onResolve={handleResolveMarker} mapRef={mapRef} />

            {activeAlert && (
              <div style={{ position: 'absolute', top: '15px', left: '50%', transform: 'translateX(-50%)', backgroundColor: '#dc2626', color: 'white', padding: '12px 25px', borderRadius: '6px', fontWeight: 'bold', boxShadow: '0 10px 15px rgba(220,38,38,0.4)', zIndex: 1000, whiteSpace: 'nowrap' }}>
                ⚠️ {activeAlert}
              </div>
            )}
          </div>

          <div style={{ position: 'absolute', bottom: '15px', left: '15px', backgroundColor: 'rgba(255,255,255,0.95)', padding: '10px 15px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '12px', color: '#334155', fontWeight: '600', zIndex: 1000 }}>
            {navData
              ? `İleri: ${navData.x_m}m | Waypoint: #${navData.waypoint_id} | ${navData.state}`
              : `İleri: ${robotPos.x.toFixed(2)}m | Bekleniyor`
            }
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '15px' }}>

          <div style={{ display: 'flex', gap: '10px' }}>
            <div style={{ flex: 1, backgroundColor: 'white', padding: '15px 5px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', textAlign: 'center', borderTop: `4px solid ${sensorBorder('temperature', '#3b82f6')}`, transition: 'border-color 0.3s' }}>
              <div style={{ color: '#475569', fontSize: '12px', marginBottom: '5px', fontWeight: 'bold' }}>SICAKLIK</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', color: hazardActive && envData?.metric === 'temperature' ? '#ef4444' : '#1e293b' }}>{sensorData.temp} °C</div>
            </div>
            <div style={{ flex: 1, backgroundColor: 'white', padding: '15px 5px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', textAlign: 'center', borderTop: `4px solid ${sensorBorder('gas_ppm', '#f59e0b')}`, transition: 'border-color 0.3s' }}>
              <div style={{ color: '#475569', fontSize: '12px', marginBottom: '5px', fontWeight: 'bold' }}>GAZ</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', color: hazardActive && envData?.metric === 'gas_ppm' ? '#ef4444' : '#1e293b' }}>{sensorData.gas} ppm</div>
            </div>
            <div style={{ flex: 1, backgroundColor: 'white', padding: '15px 5px', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', textAlign: 'center', borderTop: `4px solid ${sensorBorder('noise_db', '#10b981')}`, transition: 'border-color 0.3s' }}>
              <div style={{ color: '#475569', fontSize: '12px', marginBottom: '5px', fontWeight: 'bold' }}>GÜRÜLTÜ</div>
              <div style={{ fontSize: '20px', fontWeight: 'bold', color: hazardActive && envData?.metric === 'noise_db' ? '#ef4444' : '#1e293b' }}>{sensorData.noise} dB</div>
            </div>
          </div>

          <div style={{ flex: 1, backgroundColor: 'white', borderRadius: '10px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
            <div style={{ padding: '12px 20px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 'bold', color: '#1e293b' }}>Olay Günlüğü</span>
              <select 
                value={logFilter} 
                onChange={(e) => setLogFilter(e.target.value)}
                style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none', cursor: 'pointer' }}
              >
                <option value="ALL">Tümü</option>
                <option value="CRITICAL">Kritik Uyarılar</option>
                <option value="INFO">Bilgi Mesajları</option>
                <option value="CLEAN">Başarılı İşlemler</option>
              </select>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
              <ul style={{ listStyleType: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {events.filter(evt => logFilter === 'ALL' || evt.type === logFilter).map((evt) => (
                  <li key={evt.id} style={{
                    padding: '10px',
                    backgroundColor: evt.type === 'CRITICAL' ? '#fee2e2' : evt.type === 'CLEAN' ? '#f0fdf4' : '#f8fafc',
                    borderLeft: `4px solid ${evt.type === 'CRITICAL' ? '#ef4444' : evt.type === 'CLEAN' ? '#10b981' : '#64748b'}`,
                    borderRadius: '4px', fontSize: '13px', color: '#1e293b',
                  }}>
                    <b style={{ color: '#64748b', display: 'block', fontSize: '11px', marginBottom: '4px' }}>🗓️ {evt.time}</b> 
                    {evt.text}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div style={{ backgroundColor: 'white', borderRadius: '10px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
            <div style={{ padding: '12px 20px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontWeight: 'bold', color: '#1e293b' }}>Manuel Komut Paneli</div>
            <div style={{ padding: '15px', display: 'flex', gap: '10px' }}>
              <button
                onClick={() => sendCommand('START')}
                style={{ flex: 1, padding: '12px', backgroundColor: isMoving ? '#a7f3d0' : '#10b981', color: isMoving ? '#065f46' : 'white', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer', transition: 'background-color 0.2s' }}
              >BAŞLAT</button>
              <button
                onClick={() => sendCommand('STOP')}
                style={{ flex: 1, padding: '12px', backgroundColor: !isMoving ? '#fde68a' : '#f59e0b', color: !isMoving ? '#92400e' : 'white', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer', transition: 'background-color 0.2s' }}
              >DURDUR</button>
              <button
                onClick={() => sendCommand('ALARM')}
                style={{ flex: 1, padding: '12px', backgroundColor: '#ef4444', color: 'white', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer' }}
              >ALARM</button>
            </div>
          </div>

        </div>
      </div>

      {isCameraOpen && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          width: '640px',
          height: '480px',
          backgroundColor: '#000',
          borderRadius: '12px',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
          overflow: 'hidden',
          zIndex: 9999,
          border: '3px solid #1e293b',
          display: 'flex',
          flexDirection: 'column'
        }}>
          {/* Header Bar */}
          <div style={{ 
            backgroundColor: '#1e293b', 
            padding: '8px 12px', 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            borderBottom: '1px solid #334155'
          }}>
            <div style={{ color: 'white', fontSize: '13px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '10px', height: '10px', backgroundColor: '#ef4444', borderRadius: '50%', animation: 'pulse 1.5s infinite' }}></div>
              ROBOT KAMERASI (CANLI YAYIN)
            </div>
            <button 
              onClick={() => setIsCameraOpen(false)}
              style={{
                backgroundColor: 'transparent',
                color: '#cbd5e1',
                border: 'none',
                fontSize: '18px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '0 5px',
                transition: 'color 0.2s'
              }}
              onMouseOver={(e) => e.currentTarget.style.color = '#ef4444'}
              onMouseOut={(e) => e.currentTarget.style.color = '#cbd5e1'}
            >
              ✕
            </button>
          </div>
          
          {/* Video Container */}
          <div style={{ flex: 1, position: 'relative', backgroundColor: '#0f172a' }}>
            <img 
              src={`http://${MQTT_CONFIG.PI_IP}:8080/?action=stream`} 
              alt="Pi Camera Stream" 
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              onError={(e) => { e.target.style.display='none'; e.target.nextSibling.style.display='flex'; }}
            />
            <div style={{ display: 'none', position: 'absolute', inset: 0, justifyContent: 'center', alignItems: 'center', color: '#94a3b8', fontSize: '14px', textAlign: 'center', padding: '20px', flexDirection: 'column', gap: '10px' }}>
              <span style={{ fontSize: '24px' }}>📡</span>
              <span>Kamera bağlantısı kurulamadı.<br/>Raspberry Pi'de yayın komutunun çalıştığından emin olun.</span>
            </div>
          </div>
        </div>
      )}

      {isLogModalOpen && <LogViewerModal onClose={() => setIsLogModalOpen(false)} />}
    </div>
  )
}