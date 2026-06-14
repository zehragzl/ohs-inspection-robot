import { NodeSSH } from 'node-ssh';
import fs from 'fs';

const ssh = new NodeSSH();

async function checkPi() {
  try {
    await ssh.connect({
      host: '10.196.157.191',
      username: 'group8',
      password: process.env.PI_PASSWORD
    });

    const result = await ssh.execCommand('cat Downloads/ohs_robot/modules/mod01_ppe_stub.py');
    fs.writeFileSync('mod01_ppe_stub.py', result.stdout);
    console.log('Saved to mod01_ppe_stub.py locally');
    ssh.dispose();
  } catch (err) {
    console.error('Error connecting:', err);
  }
}

checkPi();
