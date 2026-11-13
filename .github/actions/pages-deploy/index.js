const { spawnSync } = require('node:child_process');
const path = require('node:path');

const workspace = process.env.GITHUB_WORKSPACE;
if (!workspace) {
  console.error('GITHUB_WORKSPACE is required to run the Pages deployer.');
  process.exitCode = 1;
} else {
  const wrapper = path.join(workspace, 'scripts/ci/deploy_pages_metadata_retry.py');
  const deployer = path.join(workspace, 'build/pinned-pages-deployer/dist/index.js');
  const result = spawnSync('python3', [wrapper, process.execPath, deployer], {
    env: process.env,
    shell: false,
    stdio: 'inherit',
  });

  if (result.error) {
    console.error(`Unable to launch the Pages deploy wrapper: ${result.error.message}`);
    process.exitCode = 1;
  } else if (result.signal) {
    process.kill(process.pid, result.signal);
    process.exitCode = 1;
  } else {
    process.exitCode = result.status ?? 1;
  }
}
