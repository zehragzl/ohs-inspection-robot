import { NodeSSH } from 'node-ssh';

const ssh = new NodeSSH();

async function checkPi() {
  try {
    await ssh.connect({
      host: '10.196.157.191',
      username: 'group8',
      password: process.env.PI_PASSWORD
    });
    console.log('Connected to Pi');

    const result = await ssh.execCommand('tail -n 50 Downloads/ohs_robot/robot.log');
    console.log('--- robot.log tail ---');
    console.log(result.stdout);
    if (result.stderr) console.error('STDERR:', result.stderr);
    
    // Check if main.py is running
    const ps = await ssh.execCommand('ps aux | grep main.py | grep -v grep');
    console.log('--- ps aux ---');
    console.log(ps.stdout);

    ssh.dispose();
  } catch (err) {
    console.error('Error connecting:', err);
  }
}

checkPi();
