/**
 * Tests for guard/core.mjs — TDD for human-guard distribuible.
 *
 * Mirror of test_guard.py using node:test + node:assert.
 * All times use Europe/London timezone to match the real human.md config.
 */

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { writeFileSync, readFileSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';

import {
  parseYaml,
  checkSchedule,
  startSession,
  endSession,
  checkBreak,
  cleanupOrphanSessions,
  check,
  computeSessionState,
  _setGuardDirForTest,
} from '../guard/core.mjs';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SAMPLE_YAML = `\
version: "1.1"
framework: human-md

operator:
  name: "Javi"
  timezone: "Europe/London"

schedule:
  allowed_hours:
    start: "09:00"
    end: "00:00"
  blocked_periods:
    - name: "family"
      start: "18:00"
      end: "21:00"
  wind_down:
    start: "23:30"

sessions:
  max_continuous_minutes: 150
  min_break_minutes: 15

enforcement: soft

messages:
  outside_hours: >
    Fuera de horario.
  blocked_period: >
    Tiempo de familia.
  wind_down: >
    Empieza a cerrar.
  session_limit: >
    Llevas 2h30.
  break_reminder: >
    ¿Te has levantado?
`;

const SAMPLE_CONFIG = {
  version: '1.1',
  framework: 'human-md',
  operator: { name: 'Javi', timezone: 'Europe/London' },
  schedule: {
    allowed_hours: { start: '09:00', end: '00:00' },
    blocked_periods: [{ name: 'family', start: '18:00', end: '21:00' }],
    wind_down: { start: '23:30' },
  },
  sessions: { max_continuous_minutes: 150, min_break_minutes: 15 },
  enforcement: 'soft',
  messages: {
    outside_hours: 'Fuera de horario.',
    blocked_period: 'Tiempo de familia.',
    wind_down: 'Empieza a cerrar.',
    session_limit: 'Llevas 2h30.',
    break_reminder: '¿Te has levantado?',
  },
};

// Helper: create a Date for a specific local time in a known way
// We use fake "now" objects with { hour, minute, dayOfWeek, dayName, date }
// to avoid timezone complexities in tests (same approach as Python tests using naive datetimes)
function fakeNow(year, month, day, hour, minute) {
  // Return a naive date representation matching what checkSchedule expects
  const d = new Date(year, month - 1, day, hour, minute, 0, 0);
  return d;
}

function makeTmpDir() {
  const dir = join(tmpdir(), `human-guard-test-${randomUUID().slice(0, 8)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

// ===========================================================================
// 0. YAML parser
// ===========================================================================

describe('YAML Parser', () => {
  it('empty string', () => {
    assert.deepStrictEqual(parseYaml(''), {});
  });

  it('empty whitespace', () => {
    assert.deepStrictEqual(parseYaml('   \n\n  '), {});
  });

  it('simple key-value', () => {
    const result = parseYaml('version: "1.1"');
    assert.strictEqual(result.version, '1.1');
  });

  it('unquoted string', () => {
    const result = parseYaml('framework: human-md');
    assert.strictEqual(result.framework, 'human-md');
  });

  it('integer value', () => {
    const result = parseYaml('count: 150');
    assert.strictEqual(result.count, 150);
  });

  it('nested object', () => {
    const yaml = 'operator:\n  name: "Javi"\n  timezone: "Europe/London"';
    const result = parseYaml(yaml);
    assert.strictEqual(result.operator.name, 'Javi');
    assert.strictEqual(result.operator.timezone, 'Europe/London');
  });

  it('array of objects', () => {
    const yaml = 'items:\n  - name: "family"\n    start: "18:00"\n    end: "21:00"\n';
    const result = parseYaml(yaml);
    assert.strictEqual(result.items.length, 1);
    assert.strictEqual(result.items[0].name, 'family');
    assert.strictEqual(result.items[0].start, '18:00');
  });

  it('array of scalars', () => {
    const yaml = 'days:\n  - Sunday\n  - Monday';
    const result = parseYaml(yaml);
    assert.deepStrictEqual(result.days, ['Sunday', 'Monday']);
  });

  it('folded string', () => {
    const yaml = 'msg: >\n  Hello world.\n  Second line.';
    const result = parseYaml(yaml);
    assert.ok(result.msg.includes('Hello world.'));
    assert.ok(result.msg.includes('Second line.'));
    assert.ok(!result.msg.includes('\n'));
  });

  it('comments ignored', () => {
    const yaml = '# comment\nkey: value  # inline comment';
    const result = parseYaml(yaml);
    assert.strictEqual(result.key, 'value');
  });

  it('full human.md', () => {
    const result = parseYaml(SAMPLE_YAML);
    assert.strictEqual(result.version, '1.1');
    assert.strictEqual(result.framework, 'human-md');
    assert.strictEqual(result.operator.name, 'Javi');
    assert.strictEqual(result.operator.timezone, 'Europe/London');
    assert.strictEqual(result.schedule.allowed_hours.start, '09:00');
    assert.strictEqual(result.schedule.allowed_hours.end, '00:00');
    assert.strictEqual(result.schedule.blocked_periods.length, 1);
    assert.strictEqual(result.schedule.blocked_periods[0].name, 'family');
    assert.strictEqual(result.schedule.wind_down.start, '23:30');
    assert.strictEqual(result.sessions.max_continuous_minutes, 150);
    assert.strictEqual(result.sessions.min_break_minutes, 15);
    assert.strictEqual(result.enforcement, 'soft');
    assert.ok(result.messages.outside_hours.includes('Fuera de horario.'));
  });

  it('broken yaml returns empty', () => {
    const result = parseYaml(': : : [[[');
    assert.deepStrictEqual(result, {});
  });

  it('tabs converted', () => {
    const yaml = 'key:\n\tsubkey: value';
    const result = parseYaml(yaml);
    assert.strictEqual(result.key.subkey, 'value');
  });

  it('crlf normalized', () => {
    const yaml = 'key: value\r\nother: 42';
    const result = parseYaml(yaml);
    assert.strictEqual(result.key, 'value');
    assert.strictEqual(result.other, 42);
  });

  it('multiple arrays of objects', () => {
    const yaml = 'periods:\n  - name: "lunch"\n    start: "12:00"\n    end: "13:00"\n  - name: "family"\n    start: "18:00"\n    end: "21:00"\n';
    const result = parseYaml(yaml);
    assert.strictEqual(result.periods.length, 2);
    assert.strictEqual(result.periods[0].name, 'lunch');
    assert.strictEqual(result.periods[1].name, 'family');
  });

  it('deeply nested', () => {
    const yaml = 'schedule:\n  allowed_hours:\n    start: "09:00"\n    end: "00:00"\n';
    const result = parseYaml(yaml);
    assert.strictEqual(result.schedule.allowed_hours.start, '09:00');
  });
});

// ===========================================================================
// 1. Time/schedule checking
// ===========================================================================

describe('Allowed Hours (09:00-00:00)', () => {
  it('before start → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 8, 59));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'outside_hours');
  });

  it('at start → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 9, 0));
    assert.strictEqual(result.status, 'ok');
  });

  it('midday → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(result.status, 'ok');
  });

  it('before end → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 17, 30));
    assert.strictEqual(result.status, 'ok');
  });

  it('at midnight → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 23, 0, 0));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'outside_hours');
  });

  it('deep night → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 23, 2, 0));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'outside_hours');
  });
});

describe('Blocked Periods (family 18:00-21:00)', () => {
  it('before blocked → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 17, 59));
    assert.strictEqual(result.status, 'ok');
  });

  it('at blocked start → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 18, 0));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_period');
    assert.strictEqual(result.period_name, 'family');
  });

  it('mid blocked → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 19, 30));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_period');
  });

  it('end of blocked → blocked', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 20, 59));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_period');
  });

  it('after blocked → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 21, 0));
    assert.strictEqual(result.status, 'ok');
  });
});

describe('Wind Down (23:30)', () => {
  it('before wind-down → ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 23, 29));
    assert.strictEqual(result.status, 'ok');
  });

  it('at wind-down → wind_down', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 23, 30));
    assert.strictEqual(result.status, 'wind_down');
  });

  it('during wind-down → wind_down', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 23, 59));
    assert.strictEqual(result.status, 'wind_down');
  });
});

describe('No Blocked Periods', () => {
  it('works without blocked_periods', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '09:00', end: '18:00' } },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(result.status, 'ok');
  });
});

describe('No Wind Down', () => {
  it('works without wind_down', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '09:00', end: '00:00' } },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 22, 23, 50));
    assert.strictEqual(result.status, 'ok');
  });
});

describe('End Before Start (overnight)', () => {
  it('overnight allowed', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '22:00', end: '06:00' } },
    };
    // 23:00 → ok
    assert.strictEqual(
      checkSchedule(config, fakeNow(2026, 2, 22, 23, 0)).status,
      'ok'
    );
    // 03:00 → ok
    assert.strictEqual(
      checkSchedule(config, fakeNow(2026, 2, 23, 3, 0)).status,
      'ok'
    );
    // 12:00 → blocked
    assert.strictEqual(
      checkSchedule(config, fakeNow(2026, 2, 22, 12, 0)).status,
      'blocked'
    );
  });
});

// ===========================================================================
// 2. Session log
// ===========================================================================

describe('Session Log', () => {
  let tmpDir, logPath;

  beforeEach(() => {
    tmpDir = makeTmpDir();
    logPath = join(tmpDir, 'session-log.json');
  });

  it('start_session creates entry', () => {
    const sid = startSession(logPath, '/tmp/project', false);
    assert.ok(sid);
    const data = JSON.parse(readFileSync(logPath, 'utf-8'));
    assert.strictEqual(data.sessions.length, 1);
    assert.strictEqual(data.sessions[0].id, sid);
    assert.strictEqual(data.sessions[0].end_time, null);
  });

  it('end_session updates entry', () => {
    const sid = startSession(logPath, '/tmp/project', false);
    endSession(logPath, sid);
    const data = JSON.parse(readFileSync(logPath, 'utf-8'));
    assert.notStrictEqual(data.sessions[0].end_time, null);
  });

  it('break too short → blocked', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000);
    const logData = {
      sessions: [{
        id: 'old',
        start_time: '2026-02-22T10:00:00+00:00',
        end_time: fiveMinAgo.toISOString(),
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, false);
  });

  it('break sufficient → ok', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const twentyMinAgo = new Date(now.getTime() - 20 * 60 * 1000);
    const logData = {
      sessions: [{
        id: 'old',
        start_time: '2026-02-22T10:00:00+00:00',
        end_time: twentyMinAgo.toISOString(),
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
  });

  it('orphan session auto-closed', () => {
    const logData = {
      sessions: [{
        id: 'orphan',
        start_time: '2026-02-22T06:00:00+00:00',
        end_time: null,
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    cleanupOrphanSessions(logPath, fakeNow(2026, 2, 22, 12, 0));
    const data = JSON.parse(readFileSync(logPath, 'utf-8'));
    assert.notStrictEqual(data.sessions[0].end_time, null);
  });

  it('short session → no break required', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [{
        id: 'short',
        start_time: new Date(now.getTime() - 3 * 60 * 1000).toISOString(),
        end_time: new Date(now.getTime() - 2 * 60 * 1000).toISOString(),
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
  });

  it('short session after long → break still required', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'short',
          start_time: new Date(now.getTime() - 2 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 1 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, false);
  });

  it('empty log → graceful', () => {
    const result = checkBreak(logPath, 15, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(result.ok, true);
  });

  it('corrupt log → graceful', () => {
    writeFileSync(logPath, 'not json at all {{{');
    const result = checkBreak(logPath, 15, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(result.ok, true);
  });

  it('break skipped when active session exists', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'active-terminal2',
          start_time: new Date(now.getTime() - 10 * 60 * 1000).toISOString(),
          end_time: null,
          project_dir: '/tmp/other',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
  });

  it('break enforced when no active sessions', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, false);
  });

  it('break skipped with multiple active sessions', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 2 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'active-t2',
          start_time: new Date(now.getTime() - 30 * 60 * 1000).toISOString(),
          end_time: null,
          project_dir: '/tmp/a',
          forced: false,
        },
        {
          id: 'active-t3',
          start_time: new Date(now.getTime() - 15 * 60 * 1000).toISOString(),
          end_time: null,
          project_dir: '/tmp/b',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
  });

  it('break not skipped for orphan active session', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'orphan-active',
          start_time: new Date(now.getTime() - 5 * 3600 * 1000).toISOString(),
          end_time: null,
          project_dir: '/tmp/old',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, false);
  });

  it('break not skipped for future active session', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'future-active',
          start_time: new Date(now.getTime() + 2 * 3600 * 1000).toISOString(),
          end_time: null,
          project_dir: '/tmp/future',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, false);
  });

  it('break skipped when active session has missing end_time key', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [
        {
          id: 'long-done',
          start_time: new Date(now.getTime() - 65 * 60 * 1000).toISOString(),
          end_time: new Date(now.getTime() - 5 * 60 * 1000).toISOString(),
          project_dir: '/tmp',
          forced: false,
        },
        {
          id: 'active-no-key',
          start_time: new Date(now.getTime() - 10 * 60 * 1000).toISOString(),
          project_dir: '/tmp/other',
          forced: false,
        },
      ],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
  });
});

// ===========================================================================
// 2b. Notification markers — lifecycle
// ===========================================================================

describe('Notification Markers', () => {
  let tmpDir, logPath, guardDir, origGuardDir;

  beforeEach(() => {
    tmpDir = makeTmpDir();
    logPath = join(tmpDir, 'session-log.json');
    guardDir = join(tmpDir, 'human-guard');
    mkdirSync(guardDir, { recursive: true });
    origGuardDir = _setGuardDirForTest(guardDir);
  });

  afterEach(() => {
    _setGuardDirForTest(origGuardDir);
  });

  it('end_session cleans markers', () => {
    const sid = startSession(logPath, '/tmp', false);
    mkdirSync(join(guardDir, `.notified.session_limit.${sid}`));
    mkdirSync(join(guardDir, `.notified.warn_80.${sid}`));
    assert.ok(existsSync(join(guardDir, `.notified.session_limit.${sid}`)));

    endSession(logPath, sid);

    assert.ok(!existsSync(join(guardDir, `.notified.session_limit.${sid}`)));
    assert.ok(!existsSync(join(guardDir, `.notified.warn_80.${sid}`)));
  });

  it('end_session only cleans own markers', () => {
    const sidA = startSession(logPath, '/tmp', false);
    const sidB = startSession(logPath, '/tmp', false);
    mkdirSync(join(guardDir, `.notified.session_limit.${sidA}`));
    mkdirSync(join(guardDir, `.notified.session_limit.${sidB}`));

    endSession(logPath, sidA);

    assert.ok(!existsSync(join(guardDir, `.notified.session_limit.${sidA}`)));
    assert.ok(existsSync(join(guardDir, `.notified.session_limit.${sidB}`)));
  });

  it('orphan cleanup removes markers', () => {
    const now = new Date();
    const orphanStart = new Date(now.getTime() - 5 * 3600 * 1000).toISOString();
    const logData = {
      sessions: [{
        id: 'orphan1',
        start_time: orphanStart,
        end_time: null,
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    mkdirSync(join(guardDir, '.notified.session_limit.orphan1'));
    mkdirSync(join(guardDir, '.notified.warn_80.orphan1'));

    cleanupOrphanSessions(logPath, now);

    assert.ok(!existsSync(join(guardDir, '.notified.session_limit.orphan1')));
    assert.ok(!existsSync(join(guardDir, '.notified.warn_80.orphan1')));
  });

  it('end_session no markers no error', () => {
    const sid = startSession(logPath, '/tmp', false);
    // No markers — should not throw
    endSession(logPath, sid);
  });
});

// ===========================================================================
// 3. check() integration
// ===========================================================================

describe('Check Integration', () => {
  let tmpDir, configPath, statePath, logPath;

  beforeEach(() => {
    tmpDir = makeTmpDir();
    configPath = join(tmpDir, 'human.md');
    statePath = join(tmpDir, 'session-state.json');
    logPath = join(tmpDir, 'session-log.json');
  });

  it('no config → passthrough (exit 0)', () => {
    const rc = check(
      [join(tmpDir, 'nonexistent.md')],
      statePath,
      logPath,
      false,
      fakeNow(2026, 2, 22, 3, 0)
    );
    assert.strictEqual(rc, 0);
  });

  it('corrupt yaml → passthrough', () => {
    writeFileSync(configPath, ': : : not: valid: yaml: [[[');
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(rc, 0);
  });

  it('blocked → exit 1', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 3, 0));
    assert.strictEqual(rc, 1);
  });

  it('wind-down → exit 2', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 23, 45));
    assert.strictEqual(rc, 2);
  });

  it('ok → writes session state', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(rc, 0);
    const state = JSON.parse(readFileSync(statePath, 'utf-8'));
    assert.ok('session_id' in state);
    assert.ok('start_epoch' in state);
    assert.ok('max_epoch' in state);
    assert.ok('warn_epoch' in state);
    assert.strictEqual(state.max_epoch, state.start_epoch + 150 * 60);
    assert.strictEqual(state.warn_epoch, state.start_epoch + Math.floor(150 * 60 * 0.8));
    assert.strictEqual(state.enforcement, 'soft');
    assert.strictEqual(state.blocked_periods.length, 1);
    assert.strictEqual(state.blocked_periods[0].name, 'family');
  });

  it('force overrides block', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    const rc = check([configPath], statePath, logPath, true, fakeNow(2026, 2, 22, 3, 0));
    assert.strictEqual(rc, 0);
  });

  it('blocked period → exit 1', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 19, 0));
    assert.strictEqual(rc, 1);
  });

  it('session state has messages', () => {
    writeFileSync(configPath, SAMPLE_YAML);
    check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 12, 0));
    const state = JSON.parse(readFileSync(statePath, 'utf-8'));
    assert.ok('messages' in state);
    assert.ok('session_limit' in state.messages);
    assert.ok('wind_down' in state.messages);
    assert.ok('outside_hours' in state.messages);
    assert.ok('break_reminder' in state.messages);
    assert.ok('blocked_period' in state.messages);
  });
});

describe('Overnight Blocked Periods', () => {
  it('overnight blocked during', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '00:00', end: '23:59' },
        blocked_periods: [{ name: 'night', start: '23:00', end: '01:00' }],
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 22, 23, 30));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_period');
  });

  it('overnight blocked after midnight', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '00:00', end: '23:59' },
        blocked_periods: [{ name: 'night', start: '23:00', end: '01:00' }],
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 23, 0, 30));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_period');
  });

  it('overnight blocked end exclusive', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '00:00', end: '23:59' },
        blocked_periods: [{ name: 'night', start: '23:00', end: '01:00' }],
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 23, 1, 0));
    assert.strictEqual(result.status, 'ok');
  });
});

describe('Timezone-aware schedule (Finding 4)', () => {
  it('uses configured timezone not local time', () => {
    const config = {
      ...SAMPLE_CONFIG,
      operator: { timezone: 'America/New_York' },
      schedule: { allowed_hours: { start: '09:00', end: '23:00' } },
    };
    // 1pm UTC = 8am in New York (UTC-5) → blocked in NY
    // If code incorrectly uses GMT local time (1pm), it would say "ok"
    const utc1pm = new Date('2026-02-22T13:00:00Z');
    const result = checkSchedule(config, utc1pm, 'America/New_York');
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'outside_hours');
  });

  it('timezone allows when local would block', () => {
    const config = {
      ...SAMPLE_CONFIG,
      operator: { timezone: 'Asia/Tokyo' },
      schedule: { allowed_hours: { start: '09:00', end: '23:00' } },
    };
    // 2am UTC = 11am in Tokyo (UTC+9) → ok in Tokyo
    // If code uses GMT local time (2am), it would say "blocked"
    const utc2am = new Date('2026-02-22T02:00:00Z');
    const result = checkSchedule(config, utc2am, 'Asia/Tokyo');
    assert.strictEqual(result.status, 'ok');
  });
});

describe('Invalid Date handling (Finding 10)', () => {
  let tmpDir, logPath;
  beforeEach(() => {
    tmpDir = makeTmpDir();
    logPath = join(tmpDir, 'session-log.json');
  });

  it('invalid timestamps → no NaN', () => {
    const now = fakeNow(2026, 2, 22, 12, 0);
    const logData = {
      sessions: [{
        id: 'bad',
        start_time: 'not-a-date',
        end_time: 'also-not-a-date',
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    const result = checkBreak(logPath, 15, now);
    assert.strictEqual(result.ok, true);
    assert.ok(!isNaN(result.minutes_left));
  });

  it('invalid timestamps in cleanup → no crash', () => {
    const logData = {
      sessions: [{
        id: 'bad',
        start_time: 'garbage',
        end_time: null,
        project_dir: '/tmp',
        forced: false,
      }],
    };
    writeFileSync(logPath, JSON.stringify(logData));
    // Should not throw
    cleanupOrphanSessions(logPath, fakeNow(2026, 2, 22, 12, 0));
    const data = JSON.parse(readFileSync(logPath, 'utf-8'));
    assert.notStrictEqual(data.sessions[0].end_time, null);
  });
});

describe('Blocked Days', () => {
  it('blocked day', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { ...SAMPLE_CONFIG.schedule, blocked_days: ['Sunday'] },
    };
    // 2026-02-22 is a Sunday
    const result = checkSchedule(config, fakeNow(2026, 2, 22, 12, 0));
    assert.strictEqual(result.status, 'blocked');
    assert.strictEqual(result.reason, 'blocked_day');
  });

  it('non-blocked day', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { ...SAMPLE_CONFIG.schedule, blocked_days: ['Sunday'] },
    };
    // 2026-02-23 is a Monday
    const result = checkSchedule(config, fakeNow(2026, 2, 23, 12, 0));
    assert.strictEqual(result.status, 'ok');
  });
});

// ===========================================================================
// Finding 1: Invalid timezone crash
// ===========================================================================

describe('Invalid timezone handling (Finding 1)', () => {
  it('checkSchedule with invalid tz does not throw', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '00:00', end: '23:59' } },
    };
    // Should not throw RangeError, should fallback to UTC
    const result = checkSchedule(config, new Date('2026-02-22T12:00:00Z'), 'Invalid/Timezone');
    assert.ok(['ok', 'blocked', 'wind_down'].includes(result.status));
  });

  it('check() with invalid timezone in config does not crash', () => {
    const tmpDir = makeTmpDir();
    const configPath = join(tmpDir, 'human.md');
    const statePath = join(tmpDir, 'session-state.json');
    const logPath = join(tmpDir, 'session-log.json');
    const yaml = `\
version: "1.1"
framework: human-md
operator:
  timezone: "Not/A/Real/Timezone"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
enforcement: soft
`;
    writeFileSync(configPath, yaml);
    const rc = check([configPath], statePath, logPath, false, new Date('2026-02-22T12:00:00Z'));
    assert.ok([0, 1, 2].includes(rc));
  });

  it('computeSessionState with invalid tz does not crash', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '09:00', end: '18:00' } },
    };
    const nowEpoch = Math.floor(new Date('2026-02-22T12:00:00Z').getTime() / 1000);
    // Should not throw
    const state = computeSessionState(config, nowEpoch, 'Fake/Zone');
    assert.ok('end_allowed_epoch' in state);
  });
});

// ===========================================================================
// Finding 2: Epoch uses local date instead of timezone date
// ===========================================================================

describe('Epoch timezone date computation (Finding 2)', () => {
  it('uses timezone date not local date', () => {
    // 2026-02-22T23:30:00Z = Feb 23 12:30 in Pacific/Auckland (UTC+13)
    // end_allowed_epoch for 18:00 Auckland on Feb 23 should be > now
    const now = new Date('2026-02-22T23:30:00Z');
    const config = {
      ...SAMPLE_CONFIG,
      schedule: { allowed_hours: { start: '09:00', end: '18:00' } },
    };
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'Pacific/Auckland');
    // 18:00 Auckland on Feb 23 = 05:00 UTC Feb 23 = in the future from 23:30 UTC Feb 22
    assert.ok(
      state.end_allowed_epoch > nowEpoch,
      `end_allowed_epoch (${state.end_allowed_epoch}) should be > nowEpoch (${nowEpoch})`
    );
  });

  it('wind_down_epoch uses timezone date', () => {
    // Same scenario: 2026-02-22T23:30:00Z = Feb 23 12:30 in Auckland
    const now = new Date('2026-02-22T23:30:00Z');
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '09:00', end: '18:00' },
        wind_down: { start: '17:30' },
      },
    };
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'Pacific/Auckland');
    // wind_down at 17:30 Auckland on Feb 23 = 04:30 UTC Feb 23 = in the future
    assert.ok(
      state.wind_down_epoch > nowEpoch,
      `wind_down_epoch (${state.wind_down_epoch}) should be > nowEpoch (${nowEpoch})`
    );
  });
});

// ===========================================================================
// Finding 3: Wind-down broken for overnight schedules
// ===========================================================================

describe('Wind-down overnight (Finding 3)', () => {
  it('overnight schedule: wind_down not triggered early', () => {
    // Schedule 22:00-06:00, wind_down 05:30
    // At 23:00 → should be ok, NOT wind_down
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '05:30' },
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 22, 23, 0));
    assert.strictEqual(result.status, 'ok');
  });

  it('overnight schedule: wind_down triggered near end', () => {
    // Schedule 22:00-06:00, wind_down 05:30
    // At 05:30 → should be wind_down
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '05:30' },
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 23, 5, 30));
    assert.strictEqual(result.status, 'wind_down');
  });

  it('overnight schedule: wind_down at 05:59 near end boundary', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '05:30' },
      },
    };
    const result = checkSchedule(config, fakeNow(2026, 2, 23, 5, 59));
    assert.strictEqual(result.status, 'wind_down');
  });

  it('standard schedule: wind_down still works', () => {
    // Sanity check: standard 09:00-00:00 with wind_down 23:30
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 23, 30));
    assert.strictEqual(result.status, 'wind_down');
  });

  it('standard schedule: before wind_down still ok', () => {
    const result = checkSchedule(SAMPLE_CONFIG, fakeNow(2026, 2, 22, 23, 29));
    assert.strictEqual(result.status, 'ok');
  });
});

// ===========================================================================
// Finding 1 (Audit 3): advisory enforcement in check()
// ===========================================================================

describe('Advisory enforcement (Finding 1)', () => {
  let tmpDir, configPath, statePath, logPath;

  beforeEach(() => {
    tmpDir = makeTmpDir();
    configPath = join(tmpDir, 'human.md');
    statePath = join(tmpDir, 'session-state.json');
    logPath = join(tmpDir, 'session-log.json');
  });

  it('advisory outside hours → exit 0 (not 1)', () => {
    const yaml = `\
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "09:00"
    end: "18:00"
enforcement: advisory
`;
    writeFileSync(configPath, yaml);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 3, 0));
    assert.strictEqual(rc, 0);
  });

  it('advisory writes session-state even when blocked', () => {
    const yaml = `\
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "09:00"
    end: "18:00"
enforcement: advisory
`;
    writeFileSync(configPath, yaml);
    check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 3, 0));
    const state = JSON.parse(readFileSync(statePath, 'utf-8'));
    assert.ok('session_id' in state);
    assert.strictEqual(state.enforcement, 'advisory');
  });

  it('advisory blocked_period → exit 0', () => {
    const yaml = `\
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "00:00"
    end: "23:59"
  blocked_periods:
    - name: "family"
      start: "18:00"
      end: "21:00"
enforcement: advisory
`;
    writeFileSync(configPath, yaml);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 19, 0));
    assert.strictEqual(rc, 0);
  });

  it('soft outside hours still blocks → exit 1', () => {
    const yaml = `\
version: "1.1"
framework: human-md
operator:
  timezone: "UTC"
schedule:
  allowed_hours:
    start: "09:00"
    end: "18:00"
enforcement: soft
`;
    writeFileSync(configPath, yaml);
    const rc = check([configPath], statePath, logPath, false, fakeNow(2026, 2, 22, 3, 0));
    assert.strictEqual(rc, 1);
  });
});

// ===========================================================================
// Finding 3 (Audit 3): wind_down_epoch overnight in computeSessionState
// ===========================================================================

describe('wind_down_epoch overnight (Finding 3)', () => {
  it('session pre-midnight, wind_down post-midnight → epoch in future', () => {
    // Schedule 22:00-06:00, wind_down 05:30, session at 23:00
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '05:30' },
      },
    };
    const now = fakeNow(2026, 2, 22, 23, 0);
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'UTC');
    assert.ok(
      state.wind_down_epoch > nowEpoch,
      `wind_down_epoch (${state.wind_down_epoch}) should be > nowEpoch (${nowEpoch})`
    );
  });

  it('session post-midnight, wind_down post-midnight ahead → no adjustment', () => {
    // Schedule 22:00-06:00, wind_down 05:30, session at 03:00
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '05:30' },
      },
    };
    const now = fakeNow(2026, 2, 23, 3, 0);
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'UTC');
    assert.ok(
      state.wind_down_epoch > nowEpoch,
      `wind_down_epoch (${state.wind_down_epoch}) should be > nowEpoch (${nowEpoch})`
    );
  });

  it('pre-midnight wind_down + post-midnight session → epoch in the past', () => {
    // Schedule 22:00-06:00, wind_down 23:30, session at 01:00
    // wind_down already passed — epoch must be <= nowEpoch
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '22:00', end: '06:00' },
        wind_down: { start: '23:30' },
      },
    };
    const now = fakeNow(2026, 2, 23, 1, 0);
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'UTC');
    assert.ok(
      state.wind_down_epoch <= nowEpoch,
      `wind_down_epoch (${state.wind_down_epoch}) should be <= nowEpoch (${nowEpoch}) — already passed`
    );
  });
});

// ===========================================================================
// Finding 4 (Audit 3): blocked_periods overnight epoch anchoring
// ===========================================================================

describe('blocked_period overnight epoch anchoring (Finding 4)', () => {
  it('--force at 00:30 inside 23:00-01:00 → epoch contains now', () => {
    // blocked_period 23:00-01:00, session at 00:30
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '00:00', end: '23:59' },
        blocked_periods: [{ name: 'night', start: '23:00', end: '01:00' }],
      },
    };
    const now = fakeNow(2026, 2, 23, 0, 30);
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'UTC');
    const bp = state.blocked_periods[0];
    // nowEpoch should be inside the blocked period epoch range
    assert.ok(
      nowEpoch >= bp.start_epoch && nowEpoch < bp.end_epoch,
      `nowEpoch (${nowEpoch}) should be in [${bp.start_epoch}, ${bp.end_epoch})`
    );
  });

  it('at 12:00 outside 23:00-01:00 → epoch is for next occurrence', () => {
    const config = {
      ...SAMPLE_CONFIG,
      schedule: {
        allowed_hours: { start: '00:00', end: '23:59' },
        blocked_periods: [{ name: 'night', start: '23:00', end: '01:00' }],
      },
    };
    const now = fakeNow(2026, 2, 22, 12, 0);
    const nowEpoch = Math.floor(now.getTime() / 1000);
    const state = computeSessionState(config, nowEpoch, 'UTC');
    const bp = state.blocked_periods[0];
    // Now should NOT be in the blocked period
    assert.ok(
      nowEpoch < bp.start_epoch || nowEpoch >= bp.end_epoch,
      `nowEpoch (${nowEpoch}) should NOT be in [${bp.start_epoch}, ${bp.end_epoch})`
    );
  });
});
