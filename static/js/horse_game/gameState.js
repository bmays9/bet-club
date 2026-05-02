import {
    adjustRatingByAge
} from './initialise.js';

export let playerData = [];
export let horseData = [];
export let horsePool = [];
export let retiredHorses = [];
export let raceData = {};
export let meetingNumber = 0;
export let currentSeason = 1;
export let raceEntries = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] };

// ── SETTERS ───────────────────────────────────────────────────────────────────
export function setPlayerData(data) { playerData = data; }
export function setHorseData(data) { horseData = data; }
export function setHorsePool(data) { horsePool = data; }
export function setRaceData(data) { raceData = data; }
export function setRaceEntries(data) { raceEntries = data; }
export function setMeetingNumber(num) { meetingNumber = num; }
export function setCurrentSeason(num) { currentSeason = num; }
export function addRetiredHorses(horses) { retiredHorses = retiredHorses.concat(horses); }

// ── GETTERS ───────────────────────────────────────────────────────────────────
export function getPlayerData() { return playerData; }
export function getHorseData() { return horseData; }
export function getRaceData() { return raceData; }
export function getRaceEntries() { return raceEntries; }
export function getMeetingNumber() { return meetingNumber; }
export function getRetiredHorses() { return retiredHorses; }
export function getCurrentSeason() { return currentSeason; }

// ── SORT ──────────────────────────────────────────────────────────────────────
export function sortPlayerData() {
    playerData.sort((a, b) => (b.total || 0) - (a.total || 0));
}

// ── HORSE REST ────────────────────────────────────────────────────────────────
export function incrementHorseRest(horses) {
    for (const h of horses) h.rest++;
}
export function resetHorseRest(horses) {
    for (const h of horses) h.rest = 1;
}

// ── HORSE AGE + DEVELOPMENT ───────────────────────────────────────────────────
// Called once per season. Ages the horse AND develops its baseRating:
//   - Ages 4–6: baseRating grows (youngster improving)
//   - Age 7–8:  peak, no change
//   - Ages 9+:  baseRating slowly declines
// The applied rating (horse.rating) is then recalculated from the new baseRating
// via the age modifier, giving a combined development + age curve.
export function incrementHorseAge(horses) {
    for (const h of horses) {
        h.age++;
        h.baseRating = developBaseRating(h.baseRating, h.age);
        h.rating = adjustRatingByAge(h.baseRating, h.age);
    }
}

function developBaseRating(base, newAge) {
    // Variance so not every horse develops identically
    const rand = () => (Math.random() - 0.5) * 2; // -1 to +1

    if (newAge === 4) return Math.min(150, Math.round(base + 4 + rand() * 3));  // big improvement
    if (newAge === 5) return Math.min(150, Math.round(base + 3 + rand() * 2));  // still growing
    if (newAge === 6) return Math.min(150, Math.round(base + 1 + rand() * 2));  // maturing
    if (newAge <= 8) return Math.round(base + rand() * 1.5);                   // peak — tiny variance
    if (newAge === 9) return Math.max(60, Math.round(base - 2 + rand() * 2));   // slight decline
    if (newAge === 10) return Math.max(60, Math.round(base - 4 + rand() * 2));   // clear decline
    return base; // 11+ — shouldn't be reached (they retire)
}

// ── FITNESS MODIFIER ──────────────────────────────────────────────────────────
export function fitnessModifier(rest) {
    if (rest <= -1) return 0.85; // just ran
    if (rest === 0) return 0.88;
    if (rest === 1) return 0.93;
    if (rest === 2) return 1.00; // optimal
    if (rest === 3) return 0.97;
    if (rest === 4) return 0.94;
    if (rest === 5) return 0.91;
    return 0.88; // very long layoff
}

// ── DISTANCE HELPERS ──────────────────────────────────────────────────────────
export function getNearDistances(dist) {
    const keys = ["5f", "1m", "1m2f", "1m4f", "2m", "2m4f", "3m", "4m"];
    const i = keys.indexOf(dist);
    const near = [];
    if (i > 0) near.push(keys[i - 1]);
    if (i < keys.length - 1) near.push(keys[i + 1]);
    return near;
}

export function convertFractionalOddsToDecimal(fraction) {
    if (typeof fraction !== 'string') return Infinity;
    const [n, d] = fraction.split('/').map(Number);
    if (isNaN(n) || isNaN(d) || d === 0) return Infinity;
    return n / d;
}

// ── ENTRY CHECK ───────────────────────────────────────────────────────────────
export function allRacesHaveEntries() {
    for (let i = 0; i < 6; i++) {
        if ((raceEntries[i] || []).length === 0) return false;
    }
    return true;
}
