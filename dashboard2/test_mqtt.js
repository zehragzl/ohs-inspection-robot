import mqtt from 'mqtt';

const client = mqtt.connect('ws://10.196.157.191:9001');

client.on('connect', () => {
  console.log('Connected to broker');
  client.subscribe('ohs/camera/frame', (err) => {
    if (!err) {
      console.log('Subscribed to ohs/camera/frame');
    }
  });
});

let frameCount = 0;
client.on('message', (topic, message) => {
  if (topic === 'ohs/camera/frame') {
    frameCount++;
    const payload = message.toString();
    console.log(`Received frame ${frameCount}, length: ${payload.length}, preview: ${payload.substring(0, 50)}...`);
    if (frameCount >= 3) {
      process.exit(0);
    }
  }
});

setTimeout(() => {
  console.log(`Timeout: Received ${frameCount} frames in 5 seconds`);
  process.exit(0);
}, 5000);
