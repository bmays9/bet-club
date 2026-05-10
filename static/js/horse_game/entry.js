/**
 * entry.js — Computer race entry selection
 *
 * INFORMATION MODEL:
 *   bestDist, spread, goingPref are HIDDEN from all AI logic.
 *   The AI infers distance suitability and going preference entirely
 *   from race history. Race quality is weighted by prize money so that
 *   a win in a £25,000 class 1 race counts far more than a £3,000 seller.
 *
 * TRAINER STYLES (assigned at game start, stored on player.trainerStyle):
 *   prize_hunter    — targets highest prize races each horse is suited to
 *   grade_chaser    — hammers class 1/2 even with unproven horses
 *   conditioner     — never runs unfit horses, builds slowly
 *   experimenter    — varies distances aggressively for young/unraced horses
 *   opportunist     — enters races where the field looks weakest
 *   volume_trainer  — always fills all 3 slots, maximise coverage
 *   improver        — focuses on young horses in lower classes
 *   veteran_handler — trusts older proven horses, protects their form
 */

import {
    getNearDistances, raceEntries, playerData, horseData,
    raceData, setRaceEntries, currentSeason
} from './gameState.js';
import { shuffleArray } from './initialise.js';

// ── PUBLIC TRAINER STYLES LIST ────────────────────────────────────────────────
export const TRAINER_STYLES = [
    'prize_hunter', 'grade_chaser', 'conditioner', 'experimenter',
    'opportunist', 'volume_trainer', 'improver', 'veteran_handler'
];

// ── ENTRY HELPERS ─────────────────────────────────────────────────────────────
export function canEnterRace(playerName, horseName, raceIndex) {
    for (const entries of Object.values(raceEntries)) {
        if (entries.some(e => e.horseName === horseName)) return false;
    }
    return (raceEntries[raceIndex]?.length || 0) < 3;
}

export function enterHorse(playerName, horseName, raceIndex) {
    if (canEnterRace(playerName, horseName, raceIndex)) {
        raceEntries[raceIndex].push({ playerName, horseName });
        return true;
    }
    return false;
}

export function allRacesHaveEntries() {
    for (let i = 0; i < 6; i++) {
        if (!raceEntries[i] || raceEntries[i].length === 0) return false;
    }
    return true;
}

export function displayRaceEntries(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    let html = "";
    for (let i = 0; i < 6; i++) {
        html += `<h4>Race ${i + 1}</h4><ul>`;
        for (const entry of raceEntries[i]) {
            html += `<li>${entry.horseName} (${entry.playerName})</li>`;
        }
        html += `</ul>`;
    }
    container.innerHTML = html;
}

// ── DISTANCE UTILITIES ────────────────────────────────────────────────────────
function distanceToFurlongs(s) {
    if (!s) return 0;
    if (/^\d+f$/.test(s)) return parseInt(s);
    const m = s.match(/^(\d+)m(?:(\d+)f)?$/);
    if (!m) return 0;
    return parseInt(m[1]) * 8 + (m[2] ? parseInt(m[2]) : 0);
}

// ── RACE QUALITY WEIGHT ───────────────────────────────────────────────────────
// Higher prize money = more competitive field = result is more informative.
// Normalised so class 1 (~£20,000+ first prize) = 1.0, cheap sellers = 0.15.
function raceQualityWeight(racePrize) {
    if (!racePrize || racePrize <= 0) return 0.3; // unknown — moderate weight
    return Math.min(1.0, Math.max(0.15, racePrize / 20000));
}

// Infer race class from prize money (AI doesn't read raceclass directly,
// but can reason about it from the prize)
function inferClass(racePrize) {
    if (!racePrize) return 5;
    if (racePrize >= 20000) return 1;
    if (racePrize >= 15000) return 2;
    if (racePrize >= 10000) return 3;
    if (racePrize >= 5000) return 4;
    return 5;
}

// ── INFERRED DISTANCE SCORE ───────────────────────────────────────────────────
// AI derives distance suitability purely from race history.
// bestDist and spread are NEVER used here.
//
// Each run contributes:
//   - A position score (1st=10 → unplaced=1)
//   - Weighted by race quality (prize money)
//   - Decayed by distance gap between that run and the target race
//
// Returns a score in roughly [0, 10] — higher = better suited.
function inferredDistanceScore(horse, raceDistStr) {
    const history = horse.history || [];
    const raceFurlongs = distanceToFurlongs(raceDistStr);

    if (history.length === 0) {
        // No data — unraced horse. Very mild preference for middle distances
        // as a neutral starting assumption (not using bestDist).
        const mid = 10; // ~1m2f
        return Math.max(0, 5 - Math.abs(raceFurlongs - mid) * 0.3);
    }

    // Position → raw score
    function posScore(pos) {
        if (pos === 1) return 10;
        if (pos === 2) return 7;
        if (pos === 3) return 5;
        if (pos === 4) return 3;
        if (pos === 5) return 2;
        if (pos === 0) return 0;   // last / unplaced
        return 1;
    }

    // Decay weight by distance gap: 0 furlongs away = 1.0, 8f away = 0.0
    function distDecay(runDistStr) {
        const diff = Math.abs(distanceToFurlongs(runDistStr) - raceFurlongs);
        return Math.max(0, 1 - diff / 8);
    }

    let weightedScore = 0;
    let totalWeight = 0;

    for (const run of history) {
        const qw = raceQualityWeight(run.racePrize);
        const dw = distDecay(run.distance);
        const ps = posScore(run.position);
        const weight = qw * dw;

        // Recent runs count more — decay older results slightly
        // (index 0 = oldest, last index = most recent)
        const recencyBonus = 1.0; // could weight by run index if desired

        weightedScore += ps * weight * recencyBonus;
        totalWeight += weight;
    }

    return totalWeight > 0 ? weightedScore / totalWeight : 3;
}

// ── INFERRED GOING SCORE ──────────────────────────────────────────────────────
// AI observes position in different going conditions and infers preference.
// goingPref is NEVER used here.
//
// With few runs this is noisy — confidence grows with sample size.
// Returns a modifier in [-4, 0]: 0 = likely suits, -4 = likely doesn't suit.
function inferredGoingScore(horse, raceGoing) {
    const history = horse.history || [];
    if (history.length < 2) return 0; // not enough data to form a view

    const GOINGS = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];

    // Average position score per going condition, weighted by race quality
    const goingTotals = {};
    const goingWeights = {};

    for (const run of history) {
        if (!GOINGS.includes(run.going)) continue;
        const qw = raceQualityWeight(run.racePrize);
        const ps = run.position === 1 ? 10
            : run.position === 2 ? 7
                : run.position === 3 ? 5
                    : run.position === 4 ? 3
                        : run.position === 0 ? 0 : 1;
        goingTotals[run.going] = (goingTotals[run.going] || 0) + ps * qw;
        goingWeights[run.going] = (goingWeights[run.going] || 0) + qw;
    }

    const averages = {};
    for (const g of GOINGS) {
        if (goingWeights[g]) averages[g] = goingTotals[g] / goingWeights[g];
    }

    // If we have no data for this going, interpolate from adjacent conditions
    if (!averages[raceGoing]) {
        const idx = GOINGS.indexOf(raceGoing);
        const neighbours = [GOINGS[idx - 1], GOINGS[idx + 1]].filter(Boolean);
        const neighbourAvgs = neighbours.map(g => averages[g]).filter(v => v !== undefined);
        if (!neighbourAvgs.length) return 0;
        const interp = neighbourAvgs.reduce((a, b) => a + b, 0) / neighbourAvgs.length;
        // Slight penalty for uncertainty
        return Math.min(0, (interp - 5) * 0.3);
    }

    // Compare performance on this going vs overall average
    const allAvgs = Object.values(averages);
    const overallAvg = allAvgs.reduce((a, b) => a + b, 0) / allAvgs.length;
    const diff = averages[raceGoing] - overallAvg;

    // Only penalise if clearly worse than average; reward if clearly better
    // Cap the modifier to avoid overconfidence with small samples
    const confidence = Math.min(1, history.length / 6);
    return Math.max(-4, Math.min(2, diff * 0.4 * confidence));
}

// ── FITNESS SCORE ─────────────────────────────────────────────────────────────
// Used by AI to score horse suitability for a race.
// Mirrors the two-component logic in gameState.fitnessModifier.
function fitnessScore(horse) {
    const rest = horse.rest;

    // Component 1: rest between races
    let score;
    if (rest <= -1) score = -6;  // just ran
    else if (rest === 0) score = -4;
    else if (rest === 1) score = -1;
    else if (rest === 2) score = 4;  // optimal
    else if (rest === 3) score = 2;
    else if (rest === 4) score = 0;
    else if (rest === 5) score = -1;
    else score = -3; // very long layoff

    // Component 2: seasonal overrunning
    // AI is aware a horse run too many times will underperform —
    // so it should be reluctant to enter horses past 7 seasonal runs.
    const seasonRuns = (horse.history || []).filter(r => r.season === currentSeason).length;
    if (seasonRuns > 7) {
        const excess = seasonRuns - 7;
        score -= excess * 1.5; // escalating reluctance to enter further
    }

    // Conditioner is especially sensitive to overrunning
    return score;
}

// ── RACE QUALITY SCORE ────────────────────────────────────────────────────────
// How appropriate is this race class for this horse?
// AI uses prize money to infer class.
function classAffinityScore(horse, racePrize, style) {
    const inferredCls = inferClass(racePrize);
    const rating = horse.rating || 100;
    const wins = horse.wins || 0;
    const runs = horse.runs || 0;

    let score = 0;

    // High-rated, proven horses are wasted in cheap races
    if (rating > 120 && inferredCls >= 4) score -= 8;
    if (rating > 110 && inferredCls >= 5) score -= 6;

    // Unproven horses shouldn't be thrown into the deep end
    if (wins === 0 && runs < 4 && inferredCls <= 2) score -= 10;
    if (wins === 0 && runs < 2 && inferredCls <= 3) score -= 5;

    // Style modifiers
    if (style === 'grade_chaser' && inferredCls <= 2) score += 6;
    if (style === 'grade_chaser' && inferredCls >= 4) score -= 4;
    if (style === 'prize_hunter') score += (5 - inferredCls) * 1.5; // prefer lower class numbers
    if (style === 'improver' && inferredCls >= 3) score += 3;  // build form in easier races
    if (style === 'improver' && inferredCls <= 2) score -= 4;
    if (style === 'conditioner' && inferredCls <= 2 && runs < 6) score -= 8; // don't rush young ones

    // Prize money bonus — prize_hunter directly maximises this
    if (style === 'prize_hunter') score += Math.log10(Math.max(1, racePrize || 0)) * 2;

    return score;
}

// ── AGE / DEVELOPMENT SCORE ───────────────────────────────────────────────────
function ageStyleScore(horse, style) {
    const age = horse.age || 5;
    let score = 0;
    if (style === 'improver') {
        score += age <= 6 ? 4 : age <= 8 ? 1 : -3;
    }
    if (style === 'veteran_handler') {
        score += age >= 7 ? 4 : age >= 5 ? 1 : -3;
    }
    return score;
}

// ── MASTER SCORING FUNCTION ───────────────────────────────────────────────────
// Scores a single horse against a single race using only observable data.
// Higher score = better match.
function scoreHorseForRace(horse, race, style, currentGoing) {
    let score = 0;

    // 1. Inferred distance suitability (from history, no bestDist)
    score += inferredDistanceScore(horse, race.distance) * 3.0;

    // 2. Inferred going preference (from history, no goingPref)
    score += inferredGoingScore(horse, currentGoing) * 1.5;

    // 3. Fitness (rest + seasonal load)
    score += fitnessScore(horse) * 1.5;

    // 4. Class/prize affinity
    score += classAffinityScore(horse, race.racePrize, style);

    // 5. Age/style fit
    score += ageStyleScore(horse, style);

    // 6. Base rating — better horses should generally run in better races
    score += (horse.rating || 100) * 0.05;

    // 7. Experimenter style: actively explore unrun distances for young horses
    if (style === 'experimenter' && horse.age <= 6) {
        const runDists = new Set((horse.history || []).map(r => r.distance));
        if (!runDists.has(race.distance)) score += 4; // reward novelty
    }

    // 8. Veteran handler: strongly favour proven distances
    if (style === 'veteran_handler') {
        const winsHere = (horse.history || [])
            .filter(r => r.distance === race.distance && r.position === 1).length;
        score += winsHere * 5;
    }

    // 9. Volume trainer: slight bonus for any valid entry (fill all slots)
    if (style === 'volume_trainer') score += 1;

    return score;
}

// ── OPTIMAL ASSIGNMENT ────────────────────────────────────────────────────────
// Three-pass greedy assignment guaranteeing at least one horse per race.
//
// Pass 1: assign the single best horse to each race (highest prize first).
//         No rest filter — every horse is considered. Fitness penalty is
//         already in the score via fitnessScore(), so tired horses just
//         rank lower naturally.
// Pass 2: fill 2nd/3rd slots where style permits.
// Pass 3: GUARANTEED fallback — any race still empty gets the best remaining
//         horse, with no score threshold and no rest restriction.
//         A player owns 24 horses so there are always enough for 6 races.
function assignHorsesToRaces(playerHorses, availableRaces, style, currentGoing, slotsPerRace) {
    // Highest prize first — protect best horses for most valuable races
    const racesByPriority = [...availableRaces].sort((a, b) => b.racePrize - a.racePrize);

    const assignment = {}; // raceIndex → [horseName, ...]
    const usedHorses = new Set();
    for (const race of availableRaces) assignment[race.index] = [];

    // ── Pass 1: one best horse per race ──────────────────────────────────────
    for (const race of racesByPriority) {
        const eligible = playerHorses
            .filter(h => !usedHorses.has(h.name))
            // No rest filter here — fitnessScore() handles the penalty
            .map(h => ({ horse: h, score: scoreHorseForRace(h, race, style, currentGoing) }))
            .sort((a, b) => b.score - a.score);

        if (eligible.length > 0) {
            assignment[race.index].push(eligible[0].horse.name);
            usedHorses.add(eligible[0].horse.name);
        }
    }

    // ── Pass 2: optional extra entries (2nd/3rd slots) ───────────────────────
    const maxSlots = style === 'volume_trainer' ? 3
        : style === 'grade_chaser' ? 3
            : style === 'conditioner' ? 2  // ~8 horses: 2 per race where suitable
                : 2;

    for (const race of racesByPriority) {
        if (assignment[race.index].length >= Math.min(slotsPerRace, maxSlots)) continue;

        const eligible = playerHorses
            .filter(h => !usedHorses.has(h.name))
            .map(h => ({ horse: h, score: scoreHorseForRace(h, race, style, currentGoing) }))
            .sort((a, b) => b.score - a.score);

        for (const { horse, score } of eligible) {
            if (assignment[race.index].length >= Math.min(slotsPerRace, maxSlots)) break;
            // Conditioner skips horses that just ran in Pass 2 (not Pass 3)
            if (style === 'conditioner' && horse.rest <= 1) continue;
            // Only add extras with a reasonable score — no point entering a hopeless match
            if (score < -8) continue;
            assignment[race.index].push(horse.name);
            usedHorses.add(horse.name);
        }
    }

    // ── Pass 3: GUARANTEED — every empty race must get exactly one horse ─────
    // This pass has no restrictions: no score threshold, no rest filter,
    // no style override. It simply picks the best remaining horse.
    // Since each player owns 24 horses and only needs 6, this always succeeds.
    for (const race of availableRaces) {
        if (assignment[race.index].length > 0) continue; // already filled

        const fallback = playerHorses
            .filter(h => !usedHorses.has(h.name))
            .map(h => ({ horse: h, score: scoreHorseForRace(h, race, style, currentGoing) }))
            .sort((a, b) => b.score - a.score)[0];

        if (fallback) {
            assignment[race.index].push(fallback.horse.name);
            usedHorses.add(fallback.horse.name);
        } else {
            // Absolute last resort: all horses already used — should never happen
            // with 24 horses and 6 races, but guard against edge cases
            const anyHorse = playerHorses.find(h =>
                !Object.values(assignment).flat().includes(h.name)
                || assignment[race.index].length === 0
            );
            if (anyHorse) {
                assignment[race.index].push(anyHorse.name);
                console.warn(`Forced entry for race ${race.index}: ${anyHorse.name}`);
            }
        }
    }

    // ── Verification: log any races still empty (should never happen) ────────
    for (const race of availableRaces) {
        if (assignment[race.index].length === 0) {
            console.error(`Race ${race.index} still empty after all passes for player`);
        }
    }

    return assignment;
}

// ── OPPORTUNIST ADJUSTMENT ────────────────────────────────────────────────────
// After the initial assignment, the opportunist checks if the field in each
// race looks beatable (few strong opponents) and swaps horses accordingly.
function opportunistAdjust(assignment, playerHorses, availableRaces, currentGoing) {
    // Score each race's competitiveness from others' entries
    const raceStrength = {};
    for (const race of availableRaces) {
        const others = (raceEntries[race.index] || [])
            .map(e => horseData.find(h => h.name === e.horseName))
            .filter(Boolean);
        const avgRating = others.length
            ? others.reduce((s, h) => s + (h.rating || 100), 0) / others.length
            : 80; // empty = weak field
        raceStrength[race.index] = avgRating;
    }

    // If assigned horse's inferred score for a weaker race is acceptable, prefer it
    const usedHorses = new Set(Object.values(assignment).flat());
    for (const race of availableRaces) {
        if (assignment[race.index].length === 0) continue;
        // If this race has a stronger field than average, consider swapping for a weaker race
        const avgStrength = Object.values(raceStrength).reduce((a, b) => a + b, 0) / availableRaces.length;
        if (raceStrength[race.index] > avgStrength * 1.2) {
            // Field is notably tough — if there's a weaker race our horse would suit, swap
            const weakerRace = availableRaces
                .filter(r => r.index !== race.index && raceStrength[r.index] < raceStrength[race.index])
                .sort((a, b) => raceStrength[a.index] - raceStrength[b.index])[0];
            if (weakerRace && assignment[weakerRace.index].length < 3) {
                const horseName = assignment[race.index][0];
                assignment[race.index].splice(0, 1);
                assignment[weakerRace.index].push(horseName);
            }
        }
    }
    return assignment;
}

// ── MAIN COMPUTER SELECT ──────────────────────────────────────────────────────
export function computerSelect(playerName, meetingNumber) {
    const player = playerData.find(p => p.name === playerName);
    const style = player?.trainerStyle || 'prize_hunter';
    const playerHorses = horseData.filter(h => h.owner === playerName);
    const startIndex = meetingNumber * 6;
    const currentGoing = raceData.goings?.[meetingNumber] || 'Good';

    // Guard: if player has no horses, skip silently
    if (playerHorses.length === 0) {
        console.warn(`computerSelect: no horses found for ${playerName}`);
        return;
    }

    const availableRaces = [];
    for (let i = 0; i < 6; i++) {
        const idx = startIndex + i;
        availableRaces.push({
            index: i,
            distance: raceData.distances[idx],
            racePrize: Number(raceData.prizemoney[idx]) || 0,
            raceClass: raceData.raceclass[idx],
            name: raceData.racenames[idx]
        });
    }

    for (let i = 0; i < 6; i++) raceEntries[i] = raceEntries[i] || [];

    let assignment = assignHorsesToRaces(
        playerHorses, availableRaces, style, currentGoing, 3
    );

    if (style === 'opportunist') {
        assignment = opportunistAdjust(assignment, playerHorses, availableRaces, currentGoing);
    }

    // Write assignment to raceEntries
    for (const race of availableRaces) {
        for (const horseName of assignment[race.index]) {
            if (!raceEntries[race.index].some(e => e.horseName === horseName)) {
                raceEntries[race.index].push({ playerName, horseName });
            }
        }
    }

    // ── Hard guarantee: every race must have at least one entry from this player ──
    // This catches any edge case where assignment failed for a race.
    // Use a simple rotation through available horses as final fallback.
    const usedByPlayer = new Set(
        Object.values(raceEntries).flat()
            .filter(e => e.playerName === playerName)
            .map(e => e.horseName)
    );
    const unusedHorses = playerHorses.filter(h => !usedByPlayer.has(h.name));
    let fallbackIdx = 0;

    for (let i = 0; i < 6; i++) {
        const hasEntry = raceEntries[i].some(e => e.playerName === playerName);
        if (!hasEntry) {
            // Pick the next unused horse, or cycle through all if exhausted
            const horse = unusedHorses[fallbackIdx]
                || playerHorses[fallbackIdx % playerHorses.length];
            if (horse) {
                raceEntries[i].push({ playerName, horseName: horse.name });
                usedByPlayer.add(horse.name);
                fallbackIdx++;
                console.warn(`Fallback entry: ${horse.name} → race ${i} for ${playerName}`);
            }
        }
    }
}

// ── FALLBACK AUTO-SELECT (season 1 early meetings) ────────────────────────────
// Still used for meetings 0-2 of season 1 before any history exists.
// Now uses the scoring system even without history rather than pure index-slicing.
export function computerAutoSelect(playerName, meetingNumber) {
    // Just delegate to computerSelect — the scoring handles the no-history case
    computerSelect(playerName, meetingNumber);
}

// ── FILL EMPTY RACES — final safety net ──────────────────────────────────────
// Called after computerSelect as a final guarantee. Fills any race where this
// player has no entry. No score threshold, no style restriction — just finds
// the best available horse that hasn't been used yet this meeting.
export function fillEmptyRacesWithTiredHorses(playerName, meetingNumber) {
    const player = playerData.find(p => p.name === playerName);
    const style = player?.trainerStyle || 'prize_hunter';
    const playerHorses = horseData.filter(h => h.owner === playerName);
    const currentGoing = raceData.goings?.[meetingNumber] || 'Good';

    // Build set of horses already entered in ANY race this meeting by this player
    const usedByPlayer = new Set(
        Object.values(raceEntries).flat()
            .filter(e => e.playerName === playerName)
            .map(e => e.horseName)
    );

    for (let i = 0; i < 6; i++) {
        const alreadyIn = raceEntries[i].some(e => e.playerName === playerName);
        if (alreadyIn) continue;

        const idx = meetingNumber * 6 + i;
        const race = {
            index: i,
            distance: raceData.distances[idx],
            racePrize: Number(raceData.prizemoney[idx]) || 0
        };

        // Best unused horse by score — no threshold, any horse will do
        const candidate = playerHorses
            .filter(h => !usedByPlayer.has(h.name))
            .map(h => ({ horse: h, score: scoreHorseForRace(h, race, style, currentGoing) }))
            .sort((a, b) => b.score - a.score)[0];

        if (candidate) {
            raceEntries[i].push({ playerName, horseName: candidate.horse.name });
            usedByPlayer.add(candidate.horse.name);
        } else {
            // Absolute fallback: reuse the least-recently-used horse if stable is exhausted
            // (edge case — player has fewer than 6 horses, shouldn't happen)
            const anyHorse = playerHorses.find(h =>
                !raceEntries[i].some(e => e.horseName === h.name)
            );
            if (anyHorse) {
                raceEntries[i].push({ playerName, horseName: anyHorse.name });
                console.warn(`Last resort entry: ${anyHorse.name} in race ${i} for ${playerName}`);
            } else {
                console.error(`Cannot fill race ${i} for ${playerName} — stable exhausted`);
            }
        }
    }
}

// ── UI HELPERS ────────────────────────────────────────────────────────────────
export function getRestIndicator(rest) {
    const color = rest <= -1 ? 'red'
        : rest === 0 ? 'orange'
            : rest === 1 ? '#e6b800'
                : rest === 2 ? 'forestgreen'
                    : rest === 3 ? 'lightgreen'
                        : rest === 4 ? 'turquoise'
                            : 'tan';
    const label = rest <= -1 ? '!' : rest > 4 ? '=' : rest;
    return `<span style="display:inline-flex;align-items:center;justify-content:center;
        width:20px;height:20px;border-radius:50%;background:${color};color:white;
        font-weight:bold;font-size:11px">${label}</span>`;
}

export function getBestFinishSymbol(text) {
    // Legacy fallback — kept for compatibility
    if (typeof text !== 'string') return '';
    if (text.includes("1")) return "1";
    if (text.includes("2")) return "2";
    if (text.includes("3")) return "3";
    return text;
}

// Main distance grid cell renderer — used by displayStable
// Shows best position (number) with colour-coded background + run count superscript
export function distanceFormCell(history, distKey) {
    const runs = history.filter(r => r.distance === distKey);

    if (runs.length === 0) {
        // Never run at this distance
        return `<td class="dist-cell dist-none" title="Never run at ${distKey}"></td>`;
    }

    // Best finishing position (1 = best; 0 = unplaced/last)
    const positions = runs.map(r => r.position);
    const nonZero = positions.filter(p => p > 0);
    const bestPos = nonZero.length > 0 ? Math.min(...nonZero) : 0;
    const runCount = runs.length;

    // Colour tier
    const tier = bestPos === 0 ? 'dist-unplaced'
        : bestPos === 1 ? 'dist-win'
            : bestPos === 2 ? 'dist-second'
                : bestPos === 3 ? 'dist-third'
                    : bestPos <= 6 ? 'dist-placed'
                        : 'dist-ran';

    const label = bestPos === 0 ? '—' : bestPos;

    // Superscript run count — only show if > 1 run (1 run is implied by the cell existing)
    const sup = runCount > 1 ? `<sup style="font-size:0.55rem;opacity:0.75">${runCount}</sup>` : '';

    // Tooltip with full details
    const wins = positions.filter(p => p === 1).length;
    const placed = positions.filter(p => p > 0 && p <= 3).length;
    const tip = `${distKey}: ${runCount} run${runCount > 1 ? 's' : ''}, best ${bestPos === 0 ? 'unplaced' : bestPos + 'th'}, ${wins} win${wins !== 1 ? 's' : ''}, ${placed} place${placed !== 1 ? 's' : ''}`;

    return `<td class="dist-cell ${tier}" title="${tip}">${label}${sup}</td>`;
}

export function addDistanceFormSymbols() {
    document.querySelectorAll('.horse-distance-form').forEach(cell => {
        cell.innerHTML = getBestFinishSymbol(cell.textContent.trim());
    });
}
