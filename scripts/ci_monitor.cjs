#!/usr/bin/env node
/**
 * ci_monitor.cjs — GitHub Actions CI wrapper for observable CI operations.
 * Usage: node scripts/ci_monitor.cjs <command> [options]
 */

'use strict';

const { execSync, spawnSync } = require('child_process');
const { argv } = process;

function gh(args, opts = {}) {
  const result = spawnSync('gh', args, { encoding: 'utf8', ...opts });
  if (result.error) throw new Error(`gh not found: ${result.error.message}`);
  return result;
}

function ghJSON(args) {
  const r = gh(args);
  if (r.status !== 0) {
    console.error(r.stderr.trim());
    process.exit(r.status);
  }
  return JSON.parse(r.stdout);
}

function ghText(args) {
  const r = gh(args);
  if (r.status !== 0) {
    console.error(r.stderr.trim());
    process.exit(r.status);
  }
  return r.stdout;
}

const COMMANDS = {
  runs,
  watch,
  'fail-fast': failFast,
  'log-failed': logFailed,
  'test-summary': testSummary,
  'check-actions': checkActions,
  grep: grepLogs,
  'wait-for': waitFor,
  '--help': help,
  help,
};

function help() {
  console.log(`
ci_monitor.cjs — GitHub Actions CI wrapper

Commands:
  runs [--branch <name>]           List recent workflow runs
  watch <run-id>                   Stream a running workflow's progress
  fail-fast <run-id>               Exit non-zero immediately if run fails
  log-failed <run-id>              Print logs for failed jobs/steps
  test-summary <run-id>            Print test pass/fail counts
  check-actions [file]             Check action versions in workflow file(s)
  grep <run-id> --pattern <regex>  Search run logs for a pattern
  wait-for <run-id> <job> --keyword <text>  Wait for keyword in job logs
  --help                           Show this help
`);
}

function runs() {
  const branchIdx = argv.indexOf('--branch');
  const branch = branchIdx !== -1 ? argv[branchIdx + 1] : undefined;
  const data = ghJSON([
    'run', 'list', '--limit', '20', '--json',
    'databaseId,name,status,conclusion,headBranch,createdAt',
  ]);
  const filtered = branch ? data.filter(r => r.headBranch === branch) : data;
  const display = filtered.slice(0, 10);
  console.log('\nRecent workflow runs:\n');
  for (const run of display) {
    const status = run.conclusion || run.status;
    const icon = { success: '✅', failure: '❌', cancelled: '⚠️', in_progress: '⏳', queued: '🕐' }[status] || '❓';
    console.log(`  ${icon}  #${run.databaseId}  ${run.name}`);
    console.log(`      branch: ${run.headBranch}  status: ${status}  created: ${run.createdAt}`);
    console.log();
  }
}

function watch() {
  const runId = argv[3];
  if (!runId) { console.error('Usage: watch <run-id>'); process.exit(1); }
  console.log(`Watching run ${runId}...`);
  const r = gh(['run', 'watch', runId, '--exit-status'], { stdio: 'inherit' });
  process.exit(r.status);
}

function failFast() {
  const runId = argv[3];
  if (!runId) { console.error('Usage: fail-fast <run-id>'); process.exit(1); }
  const data = ghJSON(['run', 'view', runId, '--json', 'status,conclusion']);
  const { status, conclusion } = data;
  if (status === 'completed' && conclusion !== 'success') {
    console.error(`Run ${runId} ${conclusion}`);
    process.exit(1);
  }
  if (status === 'completed') {
    console.log(`Run ${runId} succeeded.`);
    process.exit(0);
  }
  console.log(`Run ${runId} still ${status}. Use 'watch' to follow it.`);
}

function logFailed() {
  const runId = argv[3];
  if (!runId) { console.error('Usage: log-failed <run-id>'); process.exit(1); }
  console.log(`Fetching failed job logs for run ${runId}...\n`);
  const r = gh(['run', 'view', '--log-failed', runId], { stdio: 'inherit' });
  process.exit(r.status);
}

function testSummary() {
  const runId = argv[3];
  if (!runId) { console.error('Usage: test-summary <run-id>'); process.exit(1); }
  const jobs = ghJSON(['run', 'view', runId, '--json', 'jobs']);
  let passed = 0, failed = 0, skipped = 0;
  for (const job of jobs.jobs || []) {
    for (const step of job.steps || []) {
      if (step.conclusion === 'success') passed++;
      else if (step.conclusion === 'failure') failed++;
      else if (step.conclusion === 'skipped') skipped++;
    }
  }
  console.log(`\nTest summary for run ${runId}:`);
  console.log(`  ✅ passed : ${passed}`);
  console.log(`  ❌ failed : ${failed}`);
  console.log(`  ⏭  skipped: ${skipped}\n`);
}

function checkActions() {
  const file = argv[3];
  const files = file
    ? [file]
    : execSync('find .github/workflows -name "*.yml" -o -name "*.yaml" 2>/dev/null', { encoding: 'utf8' })
        .trim().split('\n').filter(Boolean);

  const actionRe = /uses:\s+([^@\s]+)@([^\s]+)/g;
  console.log('\nAction versions in workflow files:\n');
  for (const f of files) {
    let content;
    try { content = require('fs').readFileSync(f, 'utf8'); } catch { continue; }
    console.log(`  ${f}:`);
    let m;
    while ((m = actionRe.exec(content)) !== null) {
      console.log(`    ${m[1]}@${m[2]}`);
    }
    actionRe.lastIndex = 0;
  }
}

function grepLogs() {
  const runId = argv[3];
  const patIdx = argv.indexOf('--pattern');
  const pattern = patIdx !== -1 ? argv[patIdx + 1] : undefined;
  if (!runId || !pattern) { console.error('Usage: grep <run-id> --pattern <regex>'); process.exit(1); }
  const logs = ghText(['run', 'view', '--log', runId]);
  const re = new RegExp(pattern, 'i');
  const matches = logs.split('\n').filter(l => re.test(l));
  if (matches.length === 0) {
    console.log('No matches found.');
  } else {
    console.log(`\nMatches for /${pattern}/:\n`);
    matches.forEach(l => console.log(' ', l));
  }
}

function waitFor() {
  const runId = argv[3];
  const jobName = argv[4];
  const kwIdx = argv.indexOf('--keyword');
  const keyword = kwIdx !== -1 ? argv[kwIdx + 1] : undefined;
  if (!runId || !jobName || !keyword) {
    console.error('Usage: wait-for <run-id> <job> --keyword <text>');
    process.exit(1);
  }
  const start = Date.now();
  const timeout = 10 * 60 * 1000;
  console.log(`Waiting for "${keyword}" in job "${jobName}" of run ${runId}...`);
  while (Date.now() - start < timeout) {
    const logs = ghText(['run', 'view', '--log', runId]);
    const lines = logs.split('\n').filter(l => l.includes(jobName) && l.includes(keyword));
    if (lines.length > 0) {
      console.log('\nFound:');
      lines.forEach(l => console.log(' ', l));
      process.exit(0);
    }
    execSync('sleep 15');
    process.stdout.write('.');
  }
  console.error('\nTimeout waiting for keyword.');
  process.exit(1);
}

const cmd = argv[2];
const handler = COMMANDS[cmd];
if (!handler) {
  console.error(`Unknown command: ${cmd || '(none)'}\nRun with --help for usage.`);
  process.exit(1);
}
handler();
