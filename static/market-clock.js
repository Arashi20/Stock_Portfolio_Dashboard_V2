/*
 * US market hours countdown.
 *
 * Everything here is computed in the browser, not on the server. The server
 * (Amsterdam, or wherever the app happens to be hosted) never tells the page
 * what time it is: we read the visitor's own clock and convert it into New York
 * wall time with Intl's IANA timezone database. That handles US daylight saving
 * on its own, so the countdown stays correct even in the weeks where the US and
 * Europe have already switched but the other hasn't.
 */
(function () {
    'use strict';

    const NY_TZ = 'America/New_York';

    /*
     * NYSE / Nasdaq closures are derived from the calendar rather than kept in
     * a hand-written table, so the countdown doesn't silently start promising
     * sessions on Christmas Day once a hardcoded list runs out. Every closure
     * the exchange schedules by rule is covered. Unscheduled closures - a
     * national day of mourning, a hurricane - are by nature unpredictable and
     * are not handled.
     */

    /* Saturday holidays are observed on the preceding Friday, Sunday ones on
     * the following Monday. */
    function observed(year, month, day) {
        const date = new Date(Date.UTC(year, month - 1, day));
        const weekday = date.getUTCDay();
        if (weekday === 6) {
            date.setUTCDate(date.getUTCDate() - 1);
        } else if (weekday === 0) {
            date.setUTCDate(date.getUTCDate() + 1);
        }
        return date;
    }

    /* The nth given weekday of a month; n = -1 means the last one. */
    function nthWeekdayOfMonth(year, month, weekday, n) {
        if (n > 0) {
            const first = new Date(Date.UTC(year, month - 1, 1));
            const shift = (weekday - first.getUTCDay() + 7) % 7;
            return new Date(Date.UTC(year, month - 1, 1 + shift + (n - 1) * 7));
        }
        const last = new Date(Date.UTC(year, month, 0));
        const back = (last.getUTCDay() - weekday + 7) % 7;
        last.setUTCDate(last.getUTCDate() - back);
        return last;
    }

    /* Easter Sunday, via the anonymous Gregorian computus. Needed because Good
     * Friday is the one market holiday with no fixed-calendar rule. */
    function easterSunday(year) {
        const a = year % 19;
        const b = Math.floor(year / 100);
        const c = year % 100;
        const d = Math.floor(b / 4);
        const e = b % 4;
        const f = Math.floor((b + 8) / 25);
        const g = Math.floor((b - f + 1) / 3);
        const h = (19 * a + b - d - g + 15) % 30;
        const i = Math.floor(c / 4);
        const j = c % 4;
        const l = (32 + 2 * e + 2 * i - h - j) % 7;
        const m = Math.floor((a + 11 * h + 22 * l) / 451);
        const month = Math.floor((h + l - 7 * m + 114) / 31);
        const day = ((h + l - 7 * m + 114) % 31) + 1;
        return new Date(Date.UTC(year, month - 1, day));
    }

    function toKey(date) {
        return date.toISOString().slice(0, 10);
    }

    function isWeekday(date) {
        const weekday = date.getUTCDay();
        return weekday !== 0 && weekday !== 6;
    }

    function buildHolidays(year) {
        const days = [
            nthWeekdayOfMonth(year, 1, 1, 3),                            // MLK Jr. Day
            nthWeekdayOfMonth(year, 2, 1, 3),                            // Washington's Birthday
            new Date(easterSunday(year).getTime() - 2 * 86400000),       // Good Friday
            nthWeekdayOfMonth(year, 5, 1, -1),                           // Memorial Day
            observed(year, 6, 19),                                       // Juneteenth
            observed(year, 7, 4),                                        // Independence Day
            nthWeekdayOfMonth(year, 9, 1, 1),                            // Labor Day
            nthWeekdayOfMonth(year, 11, 4, 4),                           // Thanksgiving
            observed(year, 12, 25)                                       // Christmas Day
        ];
        // New Year's Day is the one exception to the observance rule: when it
        // falls on a Saturday the exchange stays open the preceding Friday
        // rather than closing on New Year's Eve.
        if (new Date(Date.UTC(year, 0, 1)).getUTCDay() !== 6) {
            days.push(observed(year, 1, 1));
        }
        return new Set(days.map(toKey));
    }

    function buildEarlyCloses(year) {
        const days = [];

        // The Friday after Thanksgiving.
        const thanksgiving = nthWeekdayOfMonth(year, 11, 4, 4);
        days.push(new Date(thanksgiving.getTime() + 86400000));

        // July 3rd, but only when both it and the 4th are weekdays - otherwise
        // the 3rd is either a weekend or the observed holiday itself.
        const julyThird = new Date(Date.UTC(year, 6, 3));
        if (isWeekday(julyThird) && isWeekday(new Date(Date.UTC(year, 6, 4)))) {
            days.push(julyThird);
        }

        // Christmas Eve, when it falls Monday to Thursday. On a Friday the 25th
        // is a Saturday, which makes the 24th the observed holiday instead.
        const christmasEve = new Date(Date.UTC(year, 11, 24));
        const eveWeekday = christmasEve.getUTCDay();
        if (eveWeekday >= 1 && eveWeekday <= 4) {
            days.push(christmasEve);
        }

        return new Set(days.map(toKey));
    }

    // isTradingDay runs several times per tick, so results are cached per year
    // rather than recomputed on every pass.
    const holidayCache = new Map();
    const earlyCloseCache = new Map();

    function cached(cache, year, build) {
        let value = cache.get(year);
        if (!value) {
            value = build(year);
            cache.set(year, value);
        }
        return value;
    }

    function isMarketHoliday(fields) {
        return cached(holidayCache, fields.year, buildHolidays).has(dayKey(fields));
    }

    function isEarlyClose(fields) {
        return cached(earlyCloseCache, fields.year, buildEarlyCloses).has(dayKey(fields));
    }

    const OPEN_MINUTES = 9 * 60 + 30;        // 09:30 ET
    const CLOSE_MINUTES = 16 * 60;           // 16:00 ET
    const EARLY_CLOSE_MINUTES = 13 * 60;     // 13:00 ET
    const PRE_MARKET_MINUTES = 4 * 60;       // 04:00 ET
    const AFTER_HOURS_END_MINUTES = 20 * 60; // 20:00 ET

    const nyFormatter = new Intl.DateTimeFormat('en-US', {
        timeZone: NY_TZ,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        weekday: 'short',
        hour12: false
    });

    const nyClockFormatter = new Intl.DateTimeFormat('en-GB', {
        timeZone: NY_TZ,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });

    const localClockFormatter = new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });

    const localDayFormatter = new Intl.DateTimeFormat('en-GB', {
        weekday: 'short',
        day: 'numeric',
        month: 'short'
    });

    /* Break an instant into New York calendar/clock fields. */
    function nyFields(date) {
        const parts = {};
        for (const part of nyFormatter.formatToParts(date)) {
            parts[part.type] = part.value;
        }
        return {
            year: Number(parts.year),
            month: Number(parts.month),
            day: Number(parts.day),
            hour: Number(parts.hour) % 24,
            minute: Number(parts.minute),
            second: Number(parts.second),
            weekday: parts.weekday
        };
    }

    function dayKey(fields) {
        const mm = String(fields.month).padStart(2, '0');
        const dd = String(fields.day).padStart(2, '0');
        return fields.year + '-' + mm + '-' + dd;
    }

    /* New York's UTC offset at a given instant, in milliseconds. */
    function nyOffset(date) {
        const f = nyFields(date);
        const asUtc = Date.UTC(f.year, f.month - 1, f.day, f.hour, f.minute, f.second);
        return asUtc - Math.floor(date.getTime() / 1000) * 1000;
    }

    /* Turn a New York wall-clock time into a real instant. */
    function nyWallTimeToDate(year, month, day, minutesOfDay) {
        const hour = Math.floor(minutesOfDay / 60);
        const minute = minutesOfDay % 60;
        const naive = Date.UTC(year, month - 1, day, hour, minute, 0);
        // The offset depends on the instant we're solving for, so approximate
        // once and then correct with the offset actually in effect there.
        let guess = new Date(naive - nyOffset(new Date(naive)));
        guess = new Date(naive - nyOffset(guess));
        return guess;
    }

    function isTradingDay(fields) {
        const weekday = new Date(Date.UTC(fields.year, fields.month - 1, fields.day)).getUTCDay();
        if (weekday === 0 || weekday === 6) {
            return false;
        }
        return !isMarketHoliday(fields);
    }

    function closeMinutesFor(fields) {
        return isEarlyClose(fields) ? EARLY_CLOSE_MINUTES : CLOSE_MINUTES;
    }

    /* The New York calendar day `offset` days after the one in `fields`. */
    function shiftDay(fields, offset) {
        const shifted = new Date(Date.UTC(fields.year, fields.month - 1, fields.day + offset));
        return {
            year: shifted.getUTCFullYear(),
            month: shifted.getUTCMonth() + 1,
            day: shifted.getUTCDate()
        };
    }

    /* The next regular-session open at or after `date`. */
    function nextOpen(date) {
        const today = nyFields(date);
        for (let i = 0; i < 14; i++) {
            const day = shiftDay(today, i);
            if (!isTradingDay(day)) {
                continue;
            }
            const open = nyWallTimeToDate(day.year, day.month, day.day, OPEN_MINUTES);
            if (open.getTime() > date.getTime()) {
                return { at: open, day: day };
            }
        }
        return null;
    }

    function currentSession(date) {
        const f = nyFields(date);
        const minutes = f.hour * 60 + f.minute + f.second / 60;

        if (isTradingDay(f)) {
            const close = closeMinutesFor(f);
            if (minutes >= OPEN_MINUTES && minutes < close) {
                return {
                    state: 'open',
                    until: nyWallTimeToDate(f.year, f.month, f.day, close)
                };
            }
            if (minutes >= PRE_MARKET_MINUTES && minutes < OPEN_MINUTES) {
                return {
                    state: 'pre',
                    until: nyWallTimeToDate(f.year, f.month, f.day, OPEN_MINUTES)
                };
            }
            if (minutes >= close && minutes < AFTER_HOURS_END_MINUTES) {
                return { state: 'after', until: null };
            }
        }
        return { state: 'closed', until: null };
    }

    function formatDuration(ms) {
        let total = Math.max(0, Math.floor(ms / 1000));
        const days = Math.floor(total / 86400);
        total -= days * 86400;
        const hours = Math.floor(total / 3600);
        total -= hours * 3600;
        const minutes = Math.floor(total / 60);
        const seconds = total - minutes * 60;

        const pad = (n) => String(n).padStart(2, '0');
        const clock = pad(hours) + ':' + pad(minutes) + ':' + pad(seconds);
        return days > 0 ? days + 'd ' + clock : clock;
    }

    function render() {
        const root = document.getElementById('marketClock');
        if (!root) {
            return;
        }

        const statusEl = root.querySelector('[data-market-status]');
        const labelEl = root.querySelector('[data-market-countdown-label]');
        const timerEl = root.querySelector('[data-market-countdown]');
        const nyClockEl = root.querySelector('[data-market-ny-clock]');
        const localHoursEl = root.querySelector('[data-market-local-hours]');
        const nextSessionEl = root.querySelector('[data-market-next-session]');

        const now = new Date();
        const session = currentSession(now);
        const upcoming = nextOpen(now);

        root.classList.remove('is-open', 'is-pre', 'is-after', 'is-closed');
        root.classList.add('is-' + session.state);

        if (session.state === 'open') {
            statusEl.textContent = 'Open';
            labelEl.textContent = 'Closes in';
            timerEl.textContent = formatDuration(session.until - now);
        } else if (session.state === 'pre') {
            statusEl.textContent = 'Pre-market';
            labelEl.textContent = 'Opens in';
            timerEl.textContent = formatDuration(session.until - now);
        } else {
            statusEl.textContent = session.state === 'after' ? 'After-hours' : 'Closed';
            labelEl.textContent = 'Opens in';
            timerEl.textContent = upcoming ? formatDuration(upcoming.at - now) : '--:--:--';
        }

        nyClockEl.textContent = nyClockFormatter.format(now) + ' New York';

        // Show the session in the visitor's own timezone too, using the next
        // open so the offset shown is the one that will actually apply.
        const referenceDay = upcoming ? upcoming.day : nyFields(now);
        const openInstant = nyWallTimeToDate(referenceDay.year, referenceDay.month, referenceDay.day, OPEN_MINUTES);
        const closeInstant = nyWallTimeToDate(
            referenceDay.year,
            referenceDay.month,
            referenceDay.day,
            closeMinutesFor(referenceDay)
        );
        localHoursEl.textContent =
            localClockFormatter.format(openInstant) + ' - ' + localClockFormatter.format(closeInstant) + ' your time';

        if (nextSessionEl) {
            nextSessionEl.textContent = upcoming
                ? 'Next session ' + localDayFormatter.format(upcoming.at) + ', ' + localClockFormatter.format(upcoming.at)
                : '';
        }
    }

    function start() {
        render();
        setInterval(render, 1000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
