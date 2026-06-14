import express from 'express';
import cors from 'cors';
import { NodeSSH } from 'node-ssh';

const app = express();
app.use(cors());
app.use(express.json());

// TODO: Lütfen Raspberry Pi'nin SSH giriş bilgilerini buraya girin.
const SSH_CONFIG = {
  host: '10.196.157.191',
  username: 'group8', // Raspberry Pi'nin kullanıcı adını buraya girin (ör. pi veya ubuntu)
  password: process.env.PI_PASSWORD // Pi şifrenizi ortam değişkeni olarak girin
};

const ssh = new NodeSSH();

app.get('/api/start', async (req, res) => {
  try {
    await ssh.connect(SSH_CONFIG);
    console.log('SSH Bağlantısı Başarılı (START komutu gönderiliyor...)');

    // Pi üzerinde çalıştırılacak komut
    // nohup ile arka planda başlatıyoruz ki SSH kapanınca kod durmasın.
    const startCmd = `export MQTT_BROKER_HOST=10.196.157.191 && cd Downloads/ohs_robot && nohup python3 main.py > robot.log 2>&1 &`;

    const result = await ssh.execCommand(startCmd);
    console.log('START STDOUT:', result.stdout);
    console.log('START STDERR:', result.stderr);

    ssh.dispose();
    res.json({ success: true, message: 'Robot başarıyla başlatıldı.' });
  } catch (error) {
    console.error('SSH Başlatma Hatası:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

app.get('/api/stop', async (req, res) => {
  try {
    await ssh.connect(SSH_CONFIG);
    console.log('SSH Bağlantısı Başarılı (STOP komutu gönderiliyor...)');

    // Pi üzerindeki main.py sürecini sonlandıran komut
    const stopCmd = `pkill -f 'python3 main.py'`;

    const result = await ssh.execCommand(stopCmd);
    console.log('STOP STDOUT:', result.stdout);
    console.log('STOP STDERR:', result.stderr);

    ssh.dispose();
    res.json({ success: true, message: 'Robot başarıyla durduruldu.' });
  } catch (error) {
    console.error('SSH Durdurma Hatası:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

const PORT = 3001;
app.listen(PORT, () => {
  console.log(`SSH Backend sunucusu http://localhost:${PORT} adresinde çalışıyor.`);
});
