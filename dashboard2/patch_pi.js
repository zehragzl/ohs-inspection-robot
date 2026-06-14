import { NodeSSH } from 'node-ssh';

const ssh = new NodeSSH();

async function patchPi() {
  try {
    await ssh.connect({
      host: '10.196.157.191',
      username: 'group8',
      password: process.env.PI_PASSWORD
    });

    const patchCmd = `
cat << 'EOF' > patch.py
import re

with open('Downloads/ohs_robot/modules/mod01_ppe_stub.py', 'r') as f:
    content = f.read()

import_str = "import cv2\\nimport base64\\n"
if "import cv2" not in content:
    content = content.replace("import os", import_str + "import os", 1)

publish_code = """
            # --- KAMERA GORUNTUSUNU MQTT ILE GONDER ---
            try:
                frame_resized = cv2.resize(frame, (320, 240))
                ret, buffer = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                if ret:
                    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                    self._client.publish("ohs/camera/frame", jpg_as_text, qos=0)
            except Exception as e:
                self._logger.error("Frame publish error: %s", e)
            # ------------------------------------------

            result = ppe_run_inference(frame=frame)
"""

content = content.replace("            result = ppe_run_inference(frame=frame)", publish_code)

with open('Downloads/ohs_robot/modules/mod01_ppe_stub.py', 'w') as f:
    f.write(content)
EOF
python3 patch.py
rm patch.py
`;
    const res = await ssh.execCommand(patchCmd);
    console.log("Patch output:", res.stdout, res.stderr);

    // Restart the main process by killing it so nohup restarts it, or let user click start
    const killRes = await ssh.execCommand("pkill -f 'python3 main.py'");
    console.log("Killed main.py to restart:", killRes.stdout);
    
    // Actually we should start it
    await ssh.execCommand("export MQTT_BROKER_HOST=10.196.157.191 && cd Downloads/ohs_robot && nohup python3 main.py > robot.log 2>&1 &");
    console.log("Started main.py");

    ssh.dispose();
  } catch (err) {
    console.error('Error connecting:', err);
  }
}

patchPi();
