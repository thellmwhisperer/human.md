#!/usr/bin/env node
/**
 * human-guard: Enforcement layer for the human.md framework.
 *
 * Modes:
 *   --check              Verify schedule, write session-state.json (exit 0=ok, 1=blocked, 2=wind-down)
 *   --start-session      Register new session in session-log.json (prints session id)
 *   --end-session ID     Mark session as ended in session-log.json
 *   --force              Override blocks
 *   --dir PATH           Project directory
 *
 * Zero external dependencies — Node stdlib only.
 * Compatible with Node 18+, Bun, Deno.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
import { randomUUID } from 'node:crypto';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const HOME = homedir();
const CLAUDE_DIR = join(HOME, '.claude');
const GUARD_DIR = join(CLAUDE_DIR, 'human-guard');
const DEFAULT_STATE_PATH = join(CLAUDE_DIR, 'session-state.json');
const DEFAULT_LOG_PATH = join(CLAUDE_DIR, 'session-log.json');
function findRepoRoot() {
  let p = process.cwd();
  while (true) {
    if (existsSync(join(p, '.git'))) return p;
    const parent = dirname(p);
    if (parent === p) break;
    p = parent;
  }
  return null;
}

function buildConfigPaths() {
  const paths = [join(process.cwd(), 'human.md')];
  const repo = findRepoRoot();
  if (repo && repo !== process.cwd()) {
    paths.push(join(repo, 'human.md'));
  }
  paths.push(join(CLAUDE_DIR, 'human.md'));
  return paths;
}

const CONFIG_SEARCH_PATHS = buildConfigPaths();

const ORPHAN_THRESHOLD_HOURS = 4;

// ---------------------------------------------------------------------------
// Inline YAML parser (subset: human.md schema only)
// ---------------------------------------------------------------------------

function parseScalar(value) {
  value = value.trim();
  if (!value) return '';
  if ((value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  const num = parseInt(value, 10);
  if (!isNaN(num) && String(num) === value) return num;
  return value;
}

function stripInlineComment(value) {
  let inQuote = null;
  for (let i = 0; i < value.length; i++) {
    const ch = value[i];
    if (ch === '"' || ch === "'") {
      if (inQuote === ch) inQuote = null;
      else if (inQuote === null) inQuote = ch;
    } else if (ch === '#' && inQuote === null) {
      if (i > 0 && (value[i - 1] === ' ' || value[i - 1] === '\t')) {
        return value.slice(0, i).trimEnd();
      }
    }
  }
  return value;
}

function preprocessLines(text) {
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/\t/g, '  ');
  const result = [];
  for (const line of text.split('\n')) {
    const stripped = line.trimStart();
    if (!stripped || stripped.startsWith('#')) continue;
    const indent = line.length - stripped.length;
    result.push([indent, stripped]);
  }
  return result;
}

function parseMapping(lines, idx, minIndent) {
  const result = {};
  while (idx < lines.length) {
    const [indent, stripped] = lines[idx];
    if (indent < minIndent) break;
    if (!stripped.includes(':') || stripped.startsWith('- ')) break;

    const colonPos = stripped.indexOf(':');
    const key = stripped.slice(0, colonPos).trim();
    if (!key) throw new Error('Empty key');
    let rest = stripped.slice(colonPos + 1).trim();

    if (rest) rest = stripInlineComment(rest);

    if (rest === '>') {
      let [val, nextIdx] = parseFolded(lines, idx + 1, indent + 1);
      result[key] = val;
      idx = nextIdx;
    } else if (rest) {
      result[key] = parseScalar(rest);
      idx++;
    } else {
      idx++;
      if (idx < lines.length && lines[idx][0] > indent) {
        const [nextIndent, nextStripped] = lines[idx];
        if (nextStripped.startsWith('- ')) {
          let [val, nextIdx] = parseSequence(lines, idx, nextIndent);
          result[key] = val;
          idx = nextIdx;
        } else {
          let [val, nextIdx] = parseMapping(lines, idx, nextIndent);
          result[key] = val;
          idx = nextIdx;
        }
      } else {
        result[key] = null;
      }
    }
  }
  return [result, idx];
}

function parseSequence(lines, idx, minIndent) {
  const result = [];
  while (idx < lines.length) {
    const [indent, stripped] = lines[idx];
    if (indent < minIndent) break;
    if (!stripped.startsWith('- ')) break;

    const content = stripped.slice(2).trim();
    const itemIndent = indent + 2;

    if (content.includes(':') && !content.startsWith('"') && !content.startsWith("'")) {
      // Array of objects
      const colonPos = content.indexOf(':');
      const k = content.slice(0, colonPos).trim();
      let v = content.slice(colonPos + 1).trim();
      if (v) v = stripInlineComment(v);
      const obj = { [k]: parseScalar(v) };
      idx++;

      // Parse remaining keys of this object
      while (idx < lines.length) {
        const [ni, ns] = lines[idx];
        if (ni < itemIndent || ns.startsWith('- ')) break;
        if (!ns.includes(':')) break;
        const cp = ns.indexOf(':');
        const ok = ns.slice(0, cp).trim();
        let ov = ns.slice(cp + 1).trim();
        if (ov) ov = stripInlineComment(ov);

        if (ov === '>') {
          let [fv, nextIdx] = parseFolded(lines, idx + 1, ni + 1);
          obj[ok] = fv;
          idx = nextIdx;
        } else if (ov) {
          obj[ok] = parseScalar(ov);
          idx++;
        } else {
          idx++;
          if (idx < lines.length && lines[idx][0] > ni) {
            const [nni, nns] = lines[idx];
            if (nns.startsWith('- ')) {
              let [val, nextIdx] = parseSequence(lines, idx, nni);
              obj[ok] = val;
              idx = nextIdx;
            } else {
              let [val, nextIdx] = parseMapping(lines, idx, nni);
              obj[ok] = val;
              idx = nextIdx;
            }
          } else {
            obj[ok] = null;
          }
        }
      }
      result.push(obj);
    } else {
      // Scalar item
      result.push(parseScalar(content));
      idx++;
    }
  }
  return [result, idx];
}

function parseFolded(lines, idx, minIndent) {
  const parts = [];
  while (idx < lines.length) {
    const [indent, stripped] = lines[idx];
    if (indent < minIndent) break;
    parts.push(stripped);
    idx++;
  }
  return [parts.join(' '), idx];
}

export function parseYaml(text) {
  if (!text || !text.trim()) return {};
  try {
    const lines = preprocessLines(text);
    if (!lines.length) return {};
    const [result] = parseMapping(lines, 0, 0);
    return result;
  } catch {
    return {};
  }
}

// ---------------------------------------------------------------------------
// Config loading
// ---------------------------------------------------------------------------

function loadConfig(configPaths) {
  for (const p of configPaths) {
    try {
      if (!existsSync(p)) continue;
      const text = readFileSync(p, 'utf-8');
      const config = parseYaml(text);
      if (config && typeof config === 'object' && config.framework === 'human-md') {
        return config;
      }
    } catch {
      continue;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Schedule checking
// ---------------------------------------------------------------------------

function parseTime(s) {
  const [h, m] = s.split(':').map(Number);
  return { hour: h, minute: m };
}

function timeToMinutes(t) {
  return t.hour * 60 + t.minute;
}

function getNowInTimezone(now, tz) {
  if (!tz) return { minutes: now.getHours() * 60 + now.getMinutes(), dayIndex: now.getDay() };
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(now);
    const hour = parseInt(parts.find(p => p.type === 'hour').value);
    const minute = parseInt(parts.find(p => p.type === 'minute').value);
    const dayParts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, weekday: 'long',
    }).formatToParts(now);
    const dayName = dayParts.find(p => p.type === 'weekday').value;
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    return { minutes: hour * 60 + minute, dayIndex: dayNames.indexOf(dayName) };
  } catch {
    // Invalid timezone — fall back to UTC
    return { minutes: now.getUTCHours() * 60 + now.getUTCMinutes(), dayIndex: now.getUTCDay() };
  }
}

export function checkSchedule(config, now, tz = null) {
  const schedule = config.schedule || {};
  const allowed = schedule.allowed_hours || {};
  const start = parseTime(allowed.start || '00:00');
  const end = parseTime(allowed.end || '23:59');

  const { minutes: nowMinutes, dayIndex } = getNowInTimezone(now, tz);
  let startMinutes = timeToMinutes(start);
  let endMinutes = timeToMinutes(end);

  // Check blocked days first
  const blockedDays = schedule.blocked_days || [];
  if (blockedDays.length) {
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const dayName = dayNames[dayIndex];
    if (blockedDays.includes(dayName)) {
      return { status: 'blocked', reason: 'blocked_day', period_name: null };
    }
  }

  // Check allowed hours
  if (endMinutes === 0) endMinutes = 24 * 60;

  let inAllowed;
  if (startMinutes < endMinutes) {
    inAllowed = nowMinutes >= startMinutes && nowMinutes < endMinutes;
  } else {
    inAllowed = nowMinutes >= startMinutes || nowMinutes < endMinutes;
  }

  if (!inAllowed) {
    return { status: 'blocked', reason: 'outside_hours', period_name: null };
  }

  // Check blocked periods (supports overnight: start > end)
  const blockedPeriods = schedule.blocked_periods || [];
  for (const bp of blockedPeriods) {
    const bpStart = timeToMinutes(parseTime(bp.start));
    const bpEnd = timeToMinutes(parseTime(bp.end));
    let inBlocked;
    if (bpStart < bpEnd) {
      inBlocked = nowMinutes >= bpStart && nowMinutes < bpEnd;
    } else {
      // Overnight blocked period (e.g. 23:00-01:00)
      inBlocked = nowMinutes >= bpStart || nowMinutes < bpEnd;
    }
    if (inBlocked) {
      return { status: 'blocked', reason: 'blocked_period', period_name: bp.name || 'unknown' };
    }
  }

  // Check wind-down (from wdStart to end of allowed window)
  const windDown = schedule.wind_down;
  if (windDown) {
    const wdStart = timeToMinutes(parseTime(windDown.start));
    let inWindDown;
    if (wdStart < endMinutes) {
      inWindDown = nowMinutes >= wdStart && nowMinutes < endMinutes;
    } else {
      // Wind-down range wraps around midnight
      inWindDown = nowMinutes >= wdStart || nowMinutes < endMinutes;
    }
    if (inWindDown) {
      return { status: 'wind_down', reason: null, period_name: null };
    }
  }

  return { status: 'ok', reason: null, period_name: null };
}

// ---------------------------------------------------------------------------
// Session log
// ---------------------------------------------------------------------------

function loadLog(logPath) {
  try {
    if (existsSync(logPath)) {
      const data = JSON.parse(readFileSync(logPath, 'utf-8'));
      if (data && typeof data === 'object' && Array.isArray(data.sessions)) {
        return data;
      }
    }
  } catch { /* ignore */ }
  return { sessions: [] };
}

function saveLog(logPath, data) {
  mkdirSync(dirname(logPath), { recursive: true });
  writeFileSync(logPath, JSON.stringify(data, null, 2));
}

export function startSession(logPath, projectDir, forced = false) {
  const data = loadLog(logPath);
  const sid = randomUUID().replace(/-/g, '').slice(0, 8);
  data.sessions.push({
    id: sid,
    start_time: new Date().toISOString(),
    end_time: null,
    project_dir: String(projectDir),
    forced,
  });
  saveLog(logPath, data);
  return sid;
}

export function endSession(logPath, sessionId) {
  const data = loadLog(logPath);
  for (const s of data.sessions) {
    if (s.id === sessionId && s.end_time === null) {
      s.end_time = new Date().toISOString();
      break;
    }
  }
  saveLog(logPath, data);
}

export function cleanupOrphanSessions(logPath, now = null) {
  const data = loadLog(logPath);
  if (!now) now = new Date();
  const thresholdMs = ORPHAN_THRESHOLD_HOURS * 3600 * 1000;

  for (const s of data.sessions) {
    if (s.end_time !== null) continue;
    const startTime = new Date(s.start_time);
    if (isNaN(startTime.getTime())) {
      s.end_time = s.start_time || now.toISOString();
    } else if (now.getTime() - startTime.getTime() > thresholdMs) {
      s.end_time = s.start_time;
    }
  }
  saveLog(logPath, data);
}

export function checkBreak(logPath, minBreakMinutes, now = null) {
  const data = loadLog(logPath);
  if (!now) now = new Date();
  const sessions = data.sessions || [];
  if (!sessions.length) return { ok: true, minutes_left: 0 };

  // Find the most recent ended session that was long enough to warrant a break.
  // Sessions shorter than minBreakMinutes are trivial (quick open/close)
  // and shouldn't force the user to wait.
  let lastEnd = null;
  for (let i = sessions.length - 1; i >= 0; i--) {
    const s = sessions[i];
    if (s.end_time && s.start_time) {
      const end = new Date(s.end_time);
      const start = new Date(s.start_time);
      if (isNaN(end.getTime()) || isNaN(start.getTime())) continue;
      const durationMin = (end.getTime() - start.getTime()) / 60000;
      if (durationMin < minBreakMinutes) continue; // Skip trivial sessions
      lastEnd = end;
      break;
    }
  }

  if (!lastEnd) return { ok: true, minutes_left: 0 };

  const elapsedMin = (now.getTime() - lastEnd.getTime()) / 60000;
  if (elapsedMin >= minBreakMinutes) {
    return { ok: true, minutes_left: 0 };
  }
  return { ok: false, minutes_left: Math.floor(minBreakMinutes - elapsedMin) };
}

// ---------------------------------------------------------------------------
// Epoch computation for session-state.json
// ---------------------------------------------------------------------------

function getDateInTimezone(date, tz) {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(date);
    return {
      year: parseInt(parts.find(p => p.type === 'year').value),
      month: parseInt(parts.find(p => p.type === 'month').value),
      day: parseInt(parts.find(p => p.type === 'day').value),
    };
  } catch {
    // Invalid timezone — use UTC
    return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
  }
}

function timeToEpochToday(t, tz, now) {
  // Extract today's date in the TARGET timezone, not the local system date
  const { year, month, day } = getDateInTimezone(now, tz);
  const hour = String(t.hour).padStart(2, '0');
  const minute = String(t.minute).padStart(2, '0');
  const monthStr = String(month).padStart(2, '0');
  const dayStr = String(day).padStart(2, '0');
  const dateStr = `${year}-${monthStr}-${dayStr}T${hour}:${minute}:00`;

  // Get offset for this timezone
  const utcDate = new Date(dateStr + 'Z');
  const offsetMs = getOffsetMs(utcDate, tz);
  return Math.floor((utcDate.getTime() - offsetMs) / 1000);
}

function getOffsetMs(date, tz) {
  try {
    const utcStr = date.toLocaleString('en-US', { timeZone: 'UTC' });
    const localStr = date.toLocaleString('en-US', { timeZone: tz });
    return new Date(localStr).getTime() - new Date(utcStr).getTime();
  } catch {
    return 0; // Invalid timezone — treat as UTC (offset 0)
  }
}

export function computeSessionState(config, nowEpoch, tz) {
  const schedule = config.schedule || {};
  const sessions = config.sessions || {};
  const messages = config.messages || {};

  const maxMinutes = sessions.max_continuous_minutes || 150;
  const maxEpoch = nowEpoch + maxMinutes * 60;
  const warnEpoch = nowEpoch + Math.floor(maxMinutes * 60 * 0.8);

  // We need a Date object for timeToEpochToday
  const nowDate = new Date(nowEpoch * 1000);

  const allowed = schedule.allowed_hours || {};
  const startTime = parseTime(allowed.start || '00:00');
  const endTime = parseTime(allowed.end || '23:59');
  const startMinutes = timeToMinutes(startTime);
  const endMinutes = timeToMinutes(endTime);

  let windDownEpoch = 0;
  const windDown = schedule.wind_down;
  if (windDown) {
    const wdTime = parseTime(windDown.start);
    windDownEpoch = timeToEpochToday(wdTime, tz, nowDate);
    if (endMinutes !== 0 && endMinutes < startMinutes) {
      // Overnight schedule: determine which instance of wind_down is relevant
      const wdMinutes = timeToMinutes(wdTime);
      const { minutes: nowMinutes } = getNowInTimezone(nowDate, tz);
      if (wdMinutes >= startMinutes) {
        // Wind_down is in the evening portion — if we're post-midnight, use yesterday's
        if (nowMinutes < endMinutes) windDownEpoch -= 86400;
      } else {
        // Wind_down is in the morning portion — if we're pre-midnight, use tomorrow's
        if (nowMinutes >= startMinutes) windDownEpoch += 86400;
      }
    }
  }
  let endEpoch;
  if (endMinutes === 0) {
    endEpoch = timeToEpochToday({ hour: 0, minute: 0 }, tz, nowDate) + 86400;
  } else {
    endEpoch = timeToEpochToday(endTime, tz, nowDate);
    // Overnight schedule: if end < start and we're after start, end is tomorrow
    if (endMinutes < startMinutes && endEpoch <= nowEpoch) {
      endEpoch += 86400;
    }
  }

  const blockedPeriods = [];
  for (const bp of (schedule.blocked_periods || [])) {
    const bpStart = parseTime(bp.start);
    const bpEnd = parseTime(bp.end);
    let bpStartEpoch = timeToEpochToday(bpStart, tz, nowDate);
    let bpEndEpoch = timeToEpochToday(bpEnd, tz, nowDate);
    // Overnight blocked period: if end < start, end is tomorrow
    if (bpEndEpoch <= bpStartEpoch) {
      bpEndEpoch += 86400;
    }
    // If the period starts in the future but we're inside yesterday's instance,
    // shift back by one day (e.g. 23:00-01:00, now=00:30)
    if (bpStartEpoch > nowEpoch) {
      const prevStart = bpStartEpoch - 86400;
      const prevEnd = bpEndEpoch - 86400;
      if (nowEpoch >= prevStart && nowEpoch < prevEnd) {
        bpStartEpoch = prevStart;
        bpEndEpoch = prevEnd;
      }
    }
    blockedPeriods.push({
      name: bp.name || 'unknown',
      start_epoch: bpStartEpoch,
      end_epoch: bpEndEpoch,
    });
  }

  return {
    session_id: randomUUID().replace(/-/g, '').slice(0, 8),
    start_epoch: nowEpoch,
    max_epoch: maxEpoch,
    warn_epoch: warnEpoch,
    wind_down_epoch: windDownEpoch,
    end_allowed_epoch: endEpoch,
    blocked_periods: blockedPeriods,
    enforcement: config.enforcement || 'soft',
    messages: {
      session_limit: String(messages.session_limit || '').trim(),
      wind_down: String(messages.wind_down || '').trim(),
      blocked_period: String(messages.blocked_period || '').trim(),
      break_reminder: String(messages.break_reminder || '').trim(),
      outside_hours: String(messages.outside_hours || '').trim(),
    },
  };
}

// ---------------------------------------------------------------------------
// Main check() function
// ---------------------------------------------------------------------------

export function check(configPaths = null, statePath = null, logPath = null, force = false, now = null) {
  if (!configPaths) configPaths = CONFIG_SEARCH_PATHS;
  if (!statePath) statePath = DEFAULT_STATE_PATH;
  if (!logPath) logPath = DEFAULT_LOG_PATH;

  const config = loadConfig(configPaths);
  if (!config) return 0;

  let tzName = (config.operator || {}).timezone || 'UTC';
  try {
    new Intl.DateTimeFormat('en', { timeZone: tzName });
  } catch {
    tzName = 'UTC';
  }

  // Get current time
  let nowDate, nowEpoch;
  if (now) {
    // For testing: `now` is a Date object in local time
    nowDate = now;
    nowEpoch = Math.floor(now.getTime() / 1000);
  } else {
    nowDate = new Date();
    nowEpoch = Math.floor(nowDate.getTime() / 1000);
  }

  // Check schedule (pass timezone for correct hour/minute extraction)
  const result = checkSchedule(config, nowDate, tzName);
  const enforcement = config.enforcement || 'soft';

  if (result.status === 'blocked' && !force) {
    const msg = (config.messages || {})[result.reason] || '';
    if (msg) process.stderr.write(String(msg).trim() + '\n');
    if (enforcement === 'advisory') {
      // Advisory: warn but allow — write session state and proceed
      const state = computeSessionState(config, nowEpoch, tzName);
      mkdirSync(dirname(statePath), { recursive: true });
      writeFileSync(statePath, JSON.stringify(state, null, 2));
      return 0;
    }
    return 1;
  }

  if (result.status === 'wind_down' && !force) {
    const msg = (config.messages || {}).wind_down || '';
    if (msg) process.stderr.write(String(msg).trim() + '\n');
    const state = computeSessionState(config, nowEpoch, tzName);
    mkdirSync(dirname(statePath), { recursive: true });
    writeFileSync(statePath, JSON.stringify(state, null, 2));
    return 2;
  }

  // Check break
  const sessionsConfig = config.sessions || {};
  const minBreak = sessionsConfig.min_break_minutes || 15;
  cleanupOrphanSessions(logPath, nowDate);
  const breakResult = checkBreak(logPath, minBreak, nowDate);
  if (!breakResult.ok && !force) {
    if (enforcement === 'advisory') {
      process.stderr.write(`Need ${breakResult.minutes_left} more minutes of break.\n`);
      const state = computeSessionState(config, nowEpoch, tzName);
      mkdirSync(dirname(statePath), { recursive: true });
      writeFileSync(statePath, JSON.stringify(state, null, 2));
      return 0;
    }
    process.stderr.write(`Need ${breakResult.minutes_left} more minutes of break.\n`);
    return 1;
  }

  // All good — write session state
  const state = computeSessionState(config, nowEpoch, tzName);
  mkdirSync(dirname(statePath), { recursive: true });
  writeFileSync(statePath, JSON.stringify(state, null, 2));
  return 0;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { check: false, startSession: false, endSession: null, force: false, dir: '.' };
  for (let i = 2; i < argv.length; i++) {
    switch (argv[i]) {
      case '--check': args.check = true; break;
      case '--start-session': args.startSession = true; break;
      case '--end-session': if (i + 1 < argv.length) args.endSession = argv[++i]; break;
      case '--force': args.force = true; break;
      case '--dir': if (i + 1 < argv.length) args.dir = argv[++i]; break;
    }
  }
  return args;
}

function main() {
  const args = parseArgs(process.argv);

  if (args.check) {
    const rc = check(null, null, null, args.force);
    process.exit(rc);
  } else if (args.startSession) {
    const sid = startSession(DEFAULT_LOG_PATH, args.dir, args.force);
    process.stdout.write(sid + '\n');
  } else if (args.endSession) {
    endSession(DEFAULT_LOG_PATH, args.endSession);
  } else {
    process.stderr.write('Usage: core.mjs --check | --start-session | --end-session ID\n');
    process.exit(1);
  }
}

// Run main only when executed directly
const isMain = process.argv[1] && (
  import.meta.url === `file://${process.argv[1]}` ||
  import.meta.url === `file://${join(process.cwd(), process.argv[1])}`
);
if (isMain) main();
