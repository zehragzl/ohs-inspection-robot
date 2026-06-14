import { NodeSSH } from 'node-ssh';

const ssh = new NodeSSH();

async function checkPi() {
  try {
    await ssh.connect({
      host: '10.196.157.191',
      username: 'group8',
      password: process.env.PI_PASSWORD
    });

    const result = await ssh.execCommand('cat Downloads/ohs_robot/src/modules/mod01_ppe_detection/ppe_stub.py || cat Downloads/ohs_robot/main.py');
    console.log('--- Pi Python Code ---');
    console.log(result.stdout.substring(0, 5000));

    // Actually, I'll search for camera/frame in the whole project
    const grepRes = await ssh.execCommand('grep -rn "ohs/camera/frame" Downloads/ohs_robot/');
    console.log('--- Grep camera/frame ---');
    console.log(grepRes.stdout);

    ssh.dispose();
  } catch (err) {
    console.error('Error connecting:', err);
  }
}

checkPi();
