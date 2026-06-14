import React, { useState, useEffect } from 'react';
import { collection, getDocs } from 'firebase/firestore';
import { db } from './firebase';

export default function LogViewerModal({ onClose }) {
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchLogs = async () => {
      setLoading(true);
      try {
        const eventsSnap = await getDocs(collection(db, 'events'));
        const violationsSnap = await getDocs(collection(db, 'violations'));
        const hazardsSnap = await getDocs(collection(db, 'hazards'));

        const allLogs = [];

        eventsSnap.forEach(doc => {
          const data = doc.data();
          allLogs.push({ id: doc.id, category: 'EVENTS', type: data.type, time: data.timestamp, text: data.text });
        });

        violationsSnap.forEach(doc => {
          const data = doc.data();
          allLogs.push({ id: doc.id, category: 'VIOLATIONS', type: 'CRITICAL', time: data.timestamp, text: `İhlal: ${data.label} (Güven: %${data.confidence})` });
        });

        hazardsSnap.forEach(doc => {
          const data = doc.data();
          allLogs.push({ id: doc.id, category: 'HAZARDS', type: 'CRITICAL', time: data.timestamp, text: `Tehlike: ${data.metric} = ${data.value} ${data.unit}` });
        });

        // Zaman damgasına göre yeniden eskiye (descending) sırala
        allLogs.sort((a, b) => new Date(b.time) - new Date(a.time));
        
        setLogs(allLogs);
      } catch (err) {
        console.error("Loglar çekilirken hata:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();
  }, []);

  const handleDownloadCSV = () => {
    const filteredLogs = filter === 'ALL' ? logs : logs.filter(l => l.category === filter);
    
    // CSV Header + BOM for Excel UTF-8 support
    let csvContent = "\uFEFF"; // BOM
    csvContent += "Tarih,Kategori,Tur,Mesaj\n";

    filteredLogs.forEach(row => {
      const date = new Date(row.time).toLocaleString('tr-TR');
      const safeText = `"${(row.text || '').replace(/"/g, '""')}"`;
      csvContent += `${date},${row.category},${row.type},${safeText}\n`;
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `bulut_loglari_${new Date().getTime()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredLogs = filter === 'ALL' ? logs : logs.filter(l => l.category === filter);

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 9999, display: 'flex', justifyContent: 'center', alignItems: 'center', fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif' }}>
      <div style={{ width: '85%', height: '85%', backgroundColor: 'white', borderRadius: '12px', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' }}>
        
        {/* Header */}
        <div style={{ padding: '20px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>☁️</span> Bulut Log Kayıtları
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '28px', cursor: 'pointer', color: '#64748b' }}>&times;</button>
        </div>

        {/* Toolbar */}
        <div style={{ padding: '15px 20px', display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #e2e8f0', backgroundColor: '#ffffff', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '10px' }}>
            {['ALL', 'EVENTS', 'VIOLATIONS', 'HAZARDS'].map(cat => (
              <button 
                key={cat}
                onClick={() => setFilter(cat)}
                style={{
                  padding: '8px 16px',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  backgroundColor: filter === cat ? '#3b82f6' : '#f1f5f9',
                  color: filter === cat ? 'white' : '#475569',
                  transition: 'background-color 0.2s'
                }}
              >
                {cat === 'ALL' ? 'Tümü' : cat === 'EVENTS' ? 'Genel Olaylar' : cat === 'VIOLATIONS' ? 'İhlaller' : 'Çevre Tehlikeleri'}
              </button>
            ))}
          </div>

          <button 
            onClick={handleDownloadCSV}
            style={{ padding: '10px 18px', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 2px 4px rgba(16,185,129,0.3)' }}
          >
            <span>📥</span> CSV İndir
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px', backgroundColor: '#f1f5f9' }}>
          {loading ? (
            <div style={{ textAlign: 'center', marginTop: '50px', color: '#64748b', fontSize: '18px', fontWeight: 'bold' }}>
              Buluttan veriler getiriliyor...
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: 'white', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
              <thead style={{ backgroundColor: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                <tr>
                  <th style={{ padding: '12px 15px', textAlign: 'left', color: '#475569', width: '20%' }}>Tarih</th>
                  <th style={{ padding: '12px 15px', textAlign: 'left', color: '#475569', width: '15%' }}>Kategori</th>
                  <th style={{ padding: '12px 15px', textAlign: 'left', color: '#475569' }}>Mesaj</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((row) => (
                  <tr key={row.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                    <td style={{ padding: '12px 15px', color: '#64748b', fontSize: '14px', whiteSpace: 'nowrap' }}>
                      {row.time ? new Date(row.time).toLocaleString('tr-TR') : 'Bilinmeyen Zaman'}
                    </td>
                    <td style={{ padding: '12px 15px' }}>
                      <span style={{ 
                        padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold',
                        backgroundColor: row.category === 'EVENTS' ? '#e0f2fe' : row.category === 'VIOLATIONS' ? '#fee2e2' : '#fef3c7',
                        color: row.category === 'EVENTS' ? '#0369a1' : row.category === 'VIOLATIONS' ? '#b91c1c' : '#b45309'
                      }}>
                        {row.category}
                      </span>
                    </td>
                    <td style={{ padding: '12px 15px', color: '#1e293b', fontSize: '14px' }}>
                      {row.text}
                    </td>
                  </tr>
                ))}
                {filteredLogs.length === 0 && (
                  <tr>
                    <td colSpan="3" style={{ padding: '30px', textAlign: 'center', color: '#64748b', fontSize: '16px' }}>Bu kategoriye ait kayıt bulunamadı.</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

      </div>
    </div>
  );
}
