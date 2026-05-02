import {
    raceEntries, playerData, horseData, horsePool, raceData, retiredHorses,
    setRaceEntries, setHorseData, incrementHorseRest, resetHorseRest,
    incrementHorseAge, fitnessModifier, convertFractionalOddsToDecimal,
    addRetiredHorses, currentSeason
} from './gameState.js';
import { allEntries, canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries } from './entry.js';
import {
    lineups, raceTime, meeting_number, incrementMeetingNumber, resetMeetingNumber,
    displayGameState, showHistoryModal
} from './horseracing.js';
import { shuffleArray } from './initialise.js';

let gameRaceNumber = 0;
let meetingRaceNumber = 0;
let rDist = "";
let rGoing = "";
let rName = "";
let rGrade = "";
let rTime = "";
let rPrize = 0;
let entries = [];
let priceHorses = [];
let rPrizes = [];
let currentRatedHorses = [];

// ── BETTING STATE ─────────────────────────────────────────────────────────────
let currentBets = [];   // [{ playerName, horseName, type, stake, potentialWin, potentialPlace, odds, result, won }]
let humanBetPending = false;

const racecardBody = document.getElementById("racecard-body");
const racecardHeader = document.getElementById("racecard-header");
const startBtn = document.getElementById('start-race');
const nextRaceBtn = document.getElementById('next-race');

// ── PLACE TERMS ───────────────────────────────────────────────────────────────
// Standard bookmaker each-way terms by field size
const PLACE_TERMS = [
    { minRunners: 2, places: 1, fraction: 1 },   // 2–4: win only
    { minRunners: 5, places: 2, fraction: 4 },   // 5–7: 2 places 1/4
    { minRunners: 8, places: 3, fraction: 5 },   // 8–11: 3 places 1/5
    { minRunners: 12, places: 4, fraction: 4 },   // 12+: 4 places 1/4
];

function getPlaceTerms(numRunners) {
    let t = PLACE_TERMS[0];
    for (const term of PLACE_TERMS) { if (numRunners >= term.minRunners) t = term; }
    return t;
}

// ── START BUTTON ──────────────────────────────────────────────────────────────
startBtn.addEventListener('click', () => {
    humanBetPending = false;
    highlightBettingRows(false);
    updateBettingStatus('');
    document.getElementById('race-screen').classList.remove('betting-active');
    startBtn.disabled = true;
    const result = simulateRace(currentRatedHorses);
    displayResults(result);
});

// ── SHOW RACECARD ─────────────────────────────────────────────────────────────
// ── STABLE COLOURS — fixed by player slot, same every game ───────────────────
// Six vivid colours, no white or black
const STABLE_COLOURS = [
    { bg: '#1a6b3c', label: 'green' },   // player 0
    { bg: '#c0392b', label: 'red' },   // player 1
    { bg: '#1a3a8f', label: 'blue' },   // player 2
    { bg: '#d4a017', label: 'yellow' },   // player 3
    { bg: '#c0680a', label: 'orange' },   // player 4
    { bg: '#6b2fa0', label: 'purple' },   // player 5
];

function getPlayerColour(trainerName) {
    const idx = playerData.findIndex(p => p.name === trainerName);
    return idx >= 0 ? STABLE_COLOURS[idx % STABLE_COLOURS.length] : { bg: '#888', label: 'grey' };
}

function trainerPill(trainerName) {
    const c = getPlayerColour(trainerName);
    return `<span class="trainer-pill" style="background:${c.bg}" title="${trainerName}">${trainerName}</span>`;
}

function fitnessDot(rest) {
    // Same logic as getRestIndicator in entry.js — dot only, no number
    const colour = rest <= -1 ? '#c0392b'    // just ran — red
        : rest === 0 ? '#e67e22'    // one rest — orange
            : rest === 1 ? '#f1c40f'    // two rests — yellow
                : rest === 2 ? '#27ae60'    // fresh — green
                    : rest === 3 ? '#1abc9c'    // very fresh — teal
                        : '#7f8c8d';   // very long layoff — grey
    const title = rest <= -1 ? 'Just ran'
        : rest === 0 ? 'One rest'
            : rest === 1 ? 'Two rests'
                : rest === 2 ? 'Fresh'
                    : rest === 3 ? 'Very fresh'
                        : 'Long layoff';
    return `<span class="fitness-dot" style="background:${colour}" title="${title}"></span>`;
}

export function showRacecard(racenum) {
    gameRaceNumber = meeting_number * 6 + racenum;
    meetingRaceNumber = racenum;

    shuffleArray(playerData);

    document.getElementById('race-screen').style.display = "block";
    document.getElementById('race-selections').style.display = "none";
    document.getElementById('player-selections').style.display = "none";
    document.getElementById('player-stable').style.display = "none";
    document.getElementById('page-info').style.display = "none";
    racecardBody.innerHTML = "";

    rDist = raceData.distances[gameRaceNumber];
    rGoing = raceData.goings[meeting_number];
    rName = raceData.racenames[gameRaceNumber];
    rTime = raceTime[racenum];
    rPrize = Number(raceData.prizemoney[gameRaceNumber]);
    rGrade = raceData.raceclass[gameRaceNumber];
    entries = lineups[racenum];

    rPrizes = [
        Math.round(rPrize * 0.65),
        Math.round(rPrize * 0.25),
        Math.round(rPrize * 0.10)
    ];

    document.getElementById("r-time").innerHTML = `${rTime} | `;
    document.getElementById("r-name").innerHTML = rName;
    document.getElementById("r-dist").innerHTML = rDist;
    document.getElementById("r-prize").innerHTML = `£${rPrize.toLocaleString()}`;
    document.getElementById("r-runners").innerHTML = `${entries.length}`;

    const raceHorses = entries
        .map(e => horseData.find(h => h.name === e.horseName))
        .filter(Boolean);

    const ratedHorses = getHorseRatings(raceHorses, rDist, rGoing);
    priceHorses = assignFormOdds(ratedHorses, rDist);

    const drawNumbers = shuffleArray([...Array(entries.length)].map((_, i) => i + 1));

    let racecardData = entries.map((entry, i) => {
        const horse = horseData.find(h => h.name === entry.horseName);
        if (!horse) return null;
        const pricedHorse = priceHorses.find(h => h.name === horse.name);
        if (!pricedHorse) return null;
        return {
            draw: drawNumbers[i], horseName: horse.name, age: horse.age,
            trainer: entry.trainer, form: horse.form,
            odds: pricedHorse.odds,
            oddsValue: convertFractionalOddsToDecimal(pricedHorse.odds)
        };
    }).filter(Boolean).sort((a, b) => a.oddsValue - b.oddsValue);

    const placeTerms = getPlaceTerms(entries.length);
    const placeDesc = entries.length < 5
        ? 'Win only (fewer than 5 runners)'
        : `${placeTerms.places} places at 1/${placeTerms.fraction} odds`;

    // Place terms display
    const ptEl = document.getElementById('place-terms');
    if (ptEl) ptEl.innerHTML = `<small class="text-muted">Each Way terms: ${placeDesc}</small>`;

    // Racecard header
    racecardHeader.innerHTML = `
        <tr>
            <th>No.</th><th>Horse</th><th>Trainer</th><th>Fit</th><th>Form</th><th>Odds</th><th>Bet</th>
        </tr>`;

    racecardData.forEach(runner => {
        const oddsClass = runner.oddsValue <= 2 ? 'odds-fav'
            : runner.oddsValue <= 8 ? 'odds-mid'
                : 'odds-out';
        const formHtml = formatFormBadges(runner.form);
        const horse = horseData.find(h => h.name === runner.horseName);
        const fitHtml = horse ? fitnessDot(horse.rest) : '';
        racecardBody.innerHTML += `
            <tr class="bet-row" data-horse="${runner.horseName}" data-odds="${runner.odds}"
                style="cursor:pointer" title="Click to place a bet on ${runner.horseName}">
                <td>${runner.draw}</td>
                <td class="text-start">${runner.horseName} <span class="text-body-secondary small-font">(${runner.age})</span></td>
                <td>${trainerPill(runner.trainer)}</td>
                <td class="text-center">${fitHtml}</td>
                <td><a href="#" class="form-link" data-horse-name="${runner.horseName}">${formHtml}</a></td>
                <td class="${oddsClass}">${runner.odds}</td>
                <td class="bet-cell" id="betcell-${runner.horseName.replace(/\s+/g, '_')}">—</td>
            </tr>`;
    });

    currentRatedHorses = ratedHorses;
    currentBets = [];

    // Form links — stop click propagating to bet handler
    document.querySelectorAll('.form-link').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            showHistoryModal(this.getAttribute('data-horse-name'));
        });
    });

    nextRaceBtn.disabled = true;
    startBtn.disabled = false;

    // Run betting round: AI bet immediately, then wait for human
    startBettingRound();
}

// ── BETTING ROUND ─────────────────────────────────────────────────────────────
function startBettingRound() {
    // All AI players bet first (computer bets are also skipped if broke)
    for (const player of playerData) {
        if (!player.human) {
            const bet = computerPlaceBet(player);
            if (bet) recordBet(bet);
        }
    }

    // Find human players who have enough money to bet (minimum £10)
    const MIN_BET = 10;
    const humanPlayers = playerData.filter(p => p.human);
    const canBet = humanPlayers.filter(p => (p.total || 0) >= MIN_BET);
    const broke = humanPlayers.filter(p => (p.total || 0) < MIN_BET);

    if (broke.length) {
        console.log(`${broke.map(p => p.name).join(', ')} cannot bet — insufficient funds.`);
    }

    if (canBet.length > 0) {
        humanBetPending = true;
        highlightBettingRows(true);
        document.getElementById('race-screen').classList.add('betting-active');
        const names = canBet.map(p => `<strong>${p.name}</strong>`).join(', ');
        const brokeNote = broke.length
            ? ` <span class="text-warning">(${broke.map(p => p.name).join(', ')}: no funds)</span>`
            : '';
        updateBettingStatus(
            `🎯 ${names}: click a horse to bet, or click <strong>▶ Start Race</strong> to skip.${brokeNote}`
        );
    } else {
        humanBetPending = false;
        document.getElementById('race-screen').classList.remove('betting-active');
        const msg = humanPlayers.length > 0
            ? `No funds available to bet. Click <strong>▶ Start Race</strong> to continue.`
            : '';
        updateBettingStatus(msg);
    }

    renderBetsTable();
}

function highlightBettingRows(on) {
    document.querySelectorAll('.bet-row').forEach(row => {
        if (on) {
            row.classList.add('table-warning');
            row._betHandler = onBetRowClick.bind(row);
            row.addEventListener('click', row._betHandler);
        } else {
            row.classList.remove('table-warning');
            if (row._betHandler) {
                row.removeEventListener('click', row._betHandler);
                delete row._betHandler;
            }
        }
    });
}

function onBetRowClick(e) {
    if (e.target.classList.contains('form-link')) return;
    if (!humanBetPending) return;
    openBetModal(this.getAttribute('data-horse'), this.getAttribute('data-odds'));
}

function updateBettingStatus(msg) {
    const el = document.getElementById('betting-status');
    if (el) el.innerHTML = msg;
}

// ── COMPUTER BETTING ──────────────────────────────────────────────────────────
function computerPlaceBet(player) {
    const profile = player.bettingProfile || 'cautious';
    const maxStake = rPrizes[0];
    const rand = Math.random();

    // Sorted runners: favourite first
    const runners = [...priceHorses].sort((a, b) =>
        convertFractionalOddsToDecimal(a.odds) - convertFractionalOddsToDecimal(b.odds));
    if (!runners.length) return null;

    const favourite = runners[0];
    const outsiders = runners.filter(h => convertFractionalOddsToDecimal(h.odds) >= 5);
    const ownHorses = priceHorses.filter(h =>
        entries.some(e => e.horseName === h.name && e.trainer === player.name));

    let chosen = null, betType = 'win', stakeRatio = 0;

    switch (profile) {
        case 'favourite_backer':
            if (rand < 0.80) { chosen = favourite; betType = 'win'; stakeRatio = 0.3 + rand * 0.4; }
            break;

        case 'outsider':
            if (outsiders.length && rand < 0.70) {
                chosen = outsiders[Math.floor(Math.random() * outsiders.length)];
                betType = rand < 0.55 ? 'ew' : 'win';
                stakeRatio = 0.08 + rand * 0.18;
            }
            break;

        case 'each_way':
            chosen = runners[Math.floor(Math.random() * Math.min(5, runners.length))];
            betType = 'ew';
            stakeRatio = 0.12 + rand * 0.20;
            break;

        case 'high_risk':
            if (outsiders.length) {
                chosen = outsiders[Math.floor(Math.random() * outsiders.length)];
                betType = rand < 0.25 ? 'ew' : 'win';
                stakeRatio = 0.45 + rand * 0.50;
            }
            break;

        case 'form_follower': {
            const byWins = entries
                .map(e => horseData.find(h => h.name === e.horseName)).filter(Boolean)
                .sort((a, b) => (b.wins || 0) - (a.wins || 0));
            if (byWins.length && rand < 0.70) {
                chosen = priceHorses.find(h => h.name === byWins[0].name);
                betType = rand < 0.45 ? 'ew' : 'win';
                stakeRatio = 0.18 + rand * 0.28;
            }
            break;
        }

        case 'own_horse':
            if (ownHorses.length && rand < 0.85) {
                chosen = ownHorses[Math.floor(Math.random() * ownHorses.length)];
                betType = rand < 0.50 ? 'ew' : 'win';
                stakeRatio = 0.20 + rand * 0.35;
            } else if (rand < 0.35) {
                chosen = favourite; betType = 'win'; stakeRatio = 0.10 + rand * 0.15;
            }
            break;

        case 'cautious':
        default:
            if (rand < 0.45) {
                chosen = runners[Math.floor(Math.random() * Math.min(3, runners.length))];
                betType = rand < 0.35 ? 'ew' : 'win';
                stakeRatio = 0.04 + rand * 0.12;
            }
            break;
    }

    if (!chosen || stakeRatio <= 0) return null;

    // Round to nearest £10, clamp to [£10, rPrizes[0]]
    let stake = Math.round((maxStake * stakeRatio) / 10) * 10;
    stake = Math.max(10, Math.min(stake, maxStake));

    // Don't bet more than the player has
    if (stake > (player.total || 0)) stake = Math.floor((player.total || 0) / 10) * 10;
    if (stake < 10) return null;

    const { potentialWin, potentialPlace } = calcReturns(chosen.odds, stake, betType, entries.length);
    return { playerName: player.name, horseName: chosen.name, type: betType, stake, potentialWin, potentialPlace, odds: chosen.odds };
}

// ── HUMAN BET MODAL ───────────────────────────────────────────────────────────
function openBetModal(horseName, odds) {
    const human = playerData.find(p => p.human);
    if (!human) return;

    // Safety check — if they somehow have no money, don't open
    if ((human.total || 0) < 10) {
        updateBettingStatus(`No funds available to bet. Click <em>Start Race</em> to continue.`);
        humanBetPending = false;
        highlightBettingRows(false);
        return;
    }

    const placeTerms = getPlaceTerms(entries.length);
    const maxStake = rPrizes[0];
    const ewAvail = entries.length >= 5;

    document.getElementById('bet-horse-name').textContent = horseName;
    document.getElementById('bet-odds').textContent = odds;
    document.getElementById('bet-max-stake').textContent = `£${maxStake.toLocaleString()}`;
    document.getElementById('bet-balance').textContent = `£${(human.total || 0).toLocaleString()}`;
    document.getElementById('bet-stake').value = '';
    document.getElementById('bet-type').value = 'win';
    document.getElementById('bet-potential').innerHTML = '';
    document.getElementById('bet-error').textContent = '';
    document.getElementById('bet-place-info').textContent = ewAvail
        ? `Each Way: ${placeTerms.places} places at 1/${placeTerms.fraction} odds`
        : 'Each Way not available (fewer than 5 runners)';

    const ewOpt = document.getElementById('bet-type').querySelector('option[value="ew"]');
    if (ewOpt) ewOpt.disabled = !ewAvail;

    const updatePotential = () => {
        const stake = parseFloat(document.getElementById('bet-stake').value) || 0;
        const betType = document.getElementById('bet-type').value;
        if (stake <= 0) { document.getElementById('bet-potential').innerHTML = ''; return; }
        const { potentialWin, potentialPlace } = calcReturns(odds, stake, betType, entries.length);
        if (betType === 'win') {
            document.getElementById('bet-potential').innerHTML =
                `If wins: <strong class="text-success">£${potentialWin.toLocaleString()}</strong>`;
        } else {
            document.getElementById('bet-potential').innerHTML =
                `If wins: <strong class="text-success">£${potentialWin.toLocaleString()}</strong>
                 &nbsp;|&nbsp; If places: <strong class="text-primary">£${potentialPlace.toLocaleString()}</strong>
                 <br><small class="text-muted">(Two bets of £${stake} each = £${(stake * 2).toLocaleString()} total)</small>`;
        }
    };

    // Reset radio to win, disable EW if needed
    document.getElementById('bet-type-win').checked = true;
    const ewRadio = document.getElementById('bet-type-ew');
    if (ewRadio) ewRadio.disabled = !ewAvail;

    document.getElementById('bet-stake').oninput = updatePotential;
    document.getElementById('bet-type').onchange = updatePotential;

    buildQuickStakes(Math.min(maxStake, human.total || 0));

    document.getElementById('bet-confirm').onclick = () => {
        const stake = parseFloat(document.getElementById('bet-stake').value) || 0;
        const betType = document.getElementById('bet-type').value;
        const errEl = document.getElementById('bet-error');
        const totalStake = betType === 'ew' ? stake * 2 : stake;

        if (stake <= 0) { errEl.textContent = 'Please enter a valid stake.'; return; }
        if (stake > maxStake) { errEl.textContent = `Maximum stake is £${maxStake.toLocaleString()}.`; return; }
        if (totalStake > (human.total || 0)) { errEl.textContent = 'Insufficient funds.'; return; }

        errEl.textContent = '';
        const { potentialWin, potentialPlace } = calcReturns(odds, stake, betType, entries.length);
        recordBet({ playerName: human.name, horseName, type: betType, stake, potentialWin, potentialPlace, odds });
        updateBetCell(horseName, betType, stake);

        humanBetPending = false;
        highlightBettingRows(false);
        document.getElementById('race-screen').classList.remove('betting-active');
        updateBettingStatus(`✅ Bet placed on <strong>${horseName}</strong> — click <strong>▶ Start Race</strong> when ready.`);
        bootstrap.Modal.getInstance(document.getElementById('betModal')).hide();
        renderBetsTable();
    };

    new bootstrap.Modal(document.getElementById('betModal')).show();
}

// ── BET CALCULATIONS ──────────────────────────────────────────────────────────
function calcReturns(oddsStr, stake, betType, numRunners) {
    const [num, denom] = oddsStr.split('/').map(Number);
    const winReturn = Math.round(stake * (num / denom) + stake);
    const terms = getPlaceTerms(numRunners);
    const placeReturn = Math.round(stake * (num / denom / terms.fraction) + stake);

    if (betType === 'win') {
        return { potentialWin: winReturn, potentialPlace: 0 };
    } else {
        // EW = two separate bets: win leg + place leg, each at `stake`
        return {
            potentialWin: winReturn + placeReturn,  // both legs pay if horse wins
            potentialPlace: placeReturn               // only place leg pays if places but doesn't win
        };
    }
}

function recordBet(bet) {
    currentBets = currentBets.filter(b => b.playerName !== bet.playerName);
    currentBets.push(bet);
}

function renderBetsTable() {
    const tbody = document.getElementById('bets-body');
    if (!tbody) return;
    if (!currentBets.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-muted text-center small">No bets placed</td></tr>`;
        return;
    }
    tbody.innerHTML = currentBets.map(b => {
        const typeLabel = b.type === 'ew' ? 'E/W' : 'Win';
        const stakeStr = b.type === 'ew'
            ? `£${b.stake.toLocaleString()} (×2)`
            : `£${b.stake.toLocaleString()}`;
        const retStr = b.type === 'ew'
            ? `£${b.potentialWin.toLocaleString()} / £${b.potentialPlace.toLocaleString()}`
            : `£${b.potentialWin.toLocaleString()}`;
        const resultHtml = b.result
            ? `<span class="${b.won ? 'text-success fw-bold' : 'text-danger'}">${b.result}</span>`
            : '—';
        return `<tr>
            <td>${b.playerName}</td>
            <td>${b.horseName}</td>
            <td>${b.odds}</td>
            <td>${typeLabel}</td>
            <td>${stakeStr}</td>
            <td>${retStr}</td>
            <td>${resultHtml}</td>
        </tr>`;
    }).join('');
}

// ── SETTLE BETS ───────────────────────────────────────────────────────────────
function settleBets(finishingOrder) {
    const terms = getPlaceTerms(entries.length);
    const placedNames = finishingOrder.slice(0, terms.places).map(h => h.name);
    const winner = finishingOrder[0]?.name;

    currentBets.forEach(bet => {
        const pi = playerData.findIndex(p => p.name === bet.playerName);
        if (pi === -1) return;
        const player = playerData[pi];

        // Total stake out (EW = double stake)
        const totalOut = bet.type === 'ew' ? bet.stake * 2 : bet.stake;
        player.total = (player.total || 0) - totalOut;
        player.betting = (player.betting || 0) + totalOut;

        let payout = 0;
        if (bet.type === 'win') {
            if (bet.horseName === winner) payout = bet.potentialWin;
        } else {
            // EW win leg
            if (bet.horseName === winner) payout += bet.potentialWin;
            // EW place leg (only the place leg if didn't win)
            else if (placedNames.includes(bet.horseName)) payout += bet.potentialPlace;
        }

        if (payout > 0) {
            player.total = (player.total || 0) + payout;
            player.winnings = (player.winnings || 0) + payout;
        }

        bet.result = payout > 0
            ? `+£${payout.toLocaleString()}`
            : `-£${totalOut.toLocaleString()}`;
        bet.won = payout > 0;

        playerData[pi] = player;
    });
}

// ── RACE SIMULATION ───────────────────────────────────────────────────────────
function simulateRace(horses) {
    const maxVar = Math.max(...horses.map(h => h.raceRating)) / 10;
    return horses
        .map(horse => ({
            ...horse,
            finalScore: horse.raceRating + Math.random() * maxVar * (Math.random() < 0.5 ? -1 : 1)
        }))
        .sort((a, b) => b.finalScore - a.finalScore);
}

// ── DISPLAY RESULTS ───────────────────────────────────────────────────────────
function displayResults(finishingOrder) {
    racecardHeader.innerHTML = `
        <tr><th>Pos.</th><th>Horse</th><th>Trainer</th><th>Odds</th><th>Prize</th></tr>`;
    racecardBody.innerHTML = "";
    const medals = ['🥇', '🥈', '🥉'];
    finishingOrder.forEach((horse, i) => {
        const odds = priceHorses.find(h => h.name === horse.name)?.odds || "?";
        const prize = i < 3 ? `£${rPrizes[i].toLocaleString()}` : "";
        const rowClass = i === 0 ? 'result-1st' : i === 1 ? 'result-2nd' : i === 2 ? 'result-3rd' : '';
        const medal = medals[i] || '';
        racecardBody.innerHTML += `
            <tr class="${rowClass}">
                <td>${medal} ${i + 1}</td>
                <td class="text-start fw-bold">${horse.name}</td>
                <td>${horse.owner || "?"}</td>
                <td>${odds}</td>
                <td class="text-success fw-bold">${prize}</td>
            </tr>`;
    });

    updateHorseData(finishingOrder, raceData.raceclass[gameRaceNumber]);
    updatePlayerData(finishingOrder);
    settleBets(finishingOrder);
    renderBetsTable();
}

// ── UPDATE HORSE DATA ─────────────────────────────────────────────────────────
function updateHorseData(results, grade) {
    const rCourse = raceData.meetings[meeting_number];
    const curGoing = raceData.goings[meeting_number];
    results.forEach((horse, i) => {
        const hi = horseData.findIndex(h => h.name === horse.name);
        if (hi === -1) return;
        const h = horseData[hi];
        const pos = (i + 1) <= 9 ? i + 1 : 0;
        h.form = (h.form || "") + pos;
        h.formLong = (h.formLong ? h.formLong + "," : "") + `${rDist}-${curGoing}-${pos}`;
        if (pos === 1) h.wins = (h.wins || 0) + 1;
        if (!h.grade1s) h.grade1s = {};
        if (pos === 1 && grade === 1) h.grade1s[rDist] = (h.grade1s[rDist] || 0) + 1;
        h.rest = -1;
        h.runs = (h.runs || 0) + 1;
        const pm = Number(rPrizes[i]) || 0;
        h.money = (h.money || 0) + pm;
        h.history = h.history || [];
        h.history.push({ season: currentSeason, meeting: meeting_number + 1, course: rCourse, name: rName, going: curGoing, distance: rDist, position: pos, winnings: pm });
        horseData[hi] = h;
    });
    startBtn.disabled = true;
    nextRaceBtn.disabled = false;
}

// ── UPDATE PLAYER DATA ────────────────────────────────────────────────────────
function updatePlayerData(results) {
    results.forEach((horse, i) => {
        const pi = playerData.findIndex(p => p.name === horse.owner);
        if (pi === -1) return;
        const p = playerData[pi];
        if (i === 0) p.wins = (p.wins || 0) + 1;
        const prize = rPrizes[i];
        if (prize) { p.winnings = (p.winnings || 0) + Number(prize); p.total = (p.total || 0) + Number(prize); }
        const fee = rPrize * 0.1;
        p.entries = (p.entries || 0) + fee;
        p.total = (p.total || 0) - fee;
        playerData[pi] = p;
    });
}

// ── NEXT RACE / MEETING ───────────────────────────────────────────────────────
document.getElementById('next-race').addEventListener('click', handleNextRace);

function handleNextRace() {
    meetingRaceNumber++;
    if (meetingRaceNumber === 6) {
        nextRaceBtn.textContent = "Next Race";
        startBtn.disabled = true; nextRaceBtn.disabled = false;
        handleContinueToNextMeeting(); return;
    }
    nextRaceBtn.textContent = meetingRaceNumber === 5 ? "Continue" : "Next Race";
    showRacecard(meetingRaceNumber);
    startBtn.disabled = false; nextRaceBtn.disabled = true;
}

function handleContinueToNextMeeting() {
    incrementHorseRest(horseData);
    meetingRaceNumber = 0;
    const isLast = meeting_number >= raceData.meetings.length - 1;
    if (!isLast) {
        incrementMeetingNumber();
        nextRaceBtn.textContent = "Next Race"; nextRaceBtn.disabled = true; startBtn.disabled = true;
        displayGameState(meeting_number);
    } else {
        resetMeetingNumber(); newSeason(); resetHorseRest(horseData);
        nextRaceBtn.disabled = true; startBtn.disabled = true;
        displayGameState(meeting_number);
    }
}

// ── 3. FORM BADGES ────────────────────────────────────────────────────────────
function formatFormBadges(formStr) {
    if (!formStr) return '—';
    return formStr.split('').map(ch => {
        if (ch === '/') return `<span class="form-sep">/</span>`;
        const cls = ch === '1' ? 'form-1'
            : ch === '2' ? 'form-2'
                : ch === '3' ? 'form-3'
                    : ch === '0' ? 'form-0'
                        : ['4', '5', '6'].includes(ch) ? 'form-4'
                            : 'form-7';
        return `<span class="form-badge ${cls}">${ch}</span>`;
    }).join('');
}

// ── 8. BET CELL UPDATE ────────────────────────────────────────────────────────
function updateBetCell(horseName, betType, stake) {
    const safeId = horseName.replace(/\s+/g, '_');
    const cell = document.getElementById(`betcell-${safeId}`);
    if (!cell) return;
    const label = betType === 'ew' ? 'E/W' : 'Win';
    cell.innerHTML = `<span class="bet-placed-badge">${label} £${stake}</span>`;
}

// ── QUICK STAKE BUTTONS ───────────────────────────────────────────────────────
function buildQuickStakes(maxStake) {
    const el = document.getElementById('quick-stakes');
    if (!el) return;
    const amounts = [10, 50, 100, 250, 500].filter(a => a <= maxStake);
    // Also add a max button
    el.innerHTML = amounts.map(a =>
        `<button type="button" class="btn btn-outline-secondary btn-sm quick-stake-btn"
            data-amount="${a}">£${a}</button>`
    ).join('') +
        `<button type="button" class="btn btn-outline-danger btn-sm quick-stake-btn"
        data-amount="${maxStake}">Max £${maxStake.toLocaleString()}</button>`;

    el.querySelectorAll('.quick-stake-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.getElementById('bet-stake').value = this.dataset.amount;
            document.getElementById('bet-stake').dispatchEvent(new Event('input'));
        });
    });
}

// ── ODDS HELPERS ──────────────────────────────────────────────────────────────
const commonFractionalOdds = [
    [1, 10], [1, 8], [1, 6], [2, 11], [1, 5], [4, 9], [1, 4], [2, 7], [3, 10],
    [1, 3], [4, 11], [2, 5], [4, 9], [8, 15], [4, 7], [8, 13], [4, 6], [4, 5],
    [5, 6], [10, 11], [1, 1], [11, 10], [5, 4], [6, 5], [11, 8], [7, 5], [6, 4],
    [3, 2], [13, 8], [7, 4], [15, 8], [2, 1], [9, 4], [5, 2], [11, 4], [3, 1],
    [10, 3], [7, 2], [4, 1], [9, 2], [5, 1], [11, 2], [6, 1], [13, 2], [7, 1],
    [15, 2], [8, 1], [17, 2], [9, 1], [10, 1], [11, 1],
    [12, 1], [14, 1], [16, 1], [18, 1], [20, 1], [22, 1], [25, 1], [28, 1],
    [33, 1], [40, 1], [50, 1], [66, 1], [80, 1], [100, 1]
];
const commonOddsWithProb = commonFractionalOdds.map(([num, denom]) => ({ num, denom, impliedProb: denom / (num + denom) }));

function distanceToFurlongs(distStr) {
    if (!distStr) return 0;
    if (/^\d+f$/.test(distStr)) return parseInt(distStr);
    const m = distStr.match(/^(\d+)m(?:(\d+)f)?$/);
    if (!m) return 0;
    return parseInt(m[1]) * 8 + (m[2] ? parseInt(m[2]) : 0);
}

function assignFormOdds(raceHorses, targetDistanceStr) {
    const td = distanceToFurlongs(targetDistanceStr);
    const scores = raceHorses.map(h => {
        let s = h.history?.length ? 0 : 5;
        for (const r of (h.history || [])) {
            const dd = Math.abs(distanceToFurlongs(r.distance) - td);
            const dw = Math.max(0, 1 - dd / 10);
            if (!isNaN(r.position) && r.position > 0) s += Math.max(0, 10 - r.position) * dw;
        }
        if (h.age === 4) s += 1;
        else if (h.age === 5) s += 2;
        else if (h.age >= 6 && h.age <= 8) s += 3;
        else if (h.age === 9) s += 1;
        else if (h.age === 10) s += 0.5;
        if (h.rest === 1) s += 1;
        else if (h.rest === 2) s += 3;
        else if (h.rest > 2) s += 1;
        return { horse: h, score: s };
    });
    const total = scores.reduce((a, x) => a + x.score, 0) || 1;
    const over = 1 + Math.random() * 0.13 + 0.02;
    return scores.map(({ horse, score }) => {
        const p = Math.min(score / total * over, 1);
        const best = commonOddsWithProb.reduce((c, o) => Math.abs(o.impliedProb - p) < c.diff ? { ...o, diff: Math.abs(o.impliedProb - p) } : c, { diff: Infinity });
        return { name: horse.name, odds: `${best.num}/${best.denom}`, impliedProb: p };
    });
}

// ── DISTANCE / GOING MODIFIERS ────────────────────────────────────────────────
function distanceRatingModifier(bestDist, raceDist, spread) {
    const diff = raceDist - bestDist;
    if (Math.abs(diff) <= spread) return 0;
    const excess = Math.abs(diff) - spread;
    const dir = diff < 0 ? 1.5 : 1.0;
    return -(Math.pow(excess, 1.7) * 1.3 * dir);
}

function getGoingModifier(pref, actual) {
    const opts = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    return -Math.abs(opts.indexOf(pref) - opts.indexOf(actual)) * 1.5;
}

function getHorseRatings(raceHorses, distanceStr, going) {
    const raceDist = distanceToFurlongs(rDist);
    return raceHorses.map(h => {
        let r = h.rating;
        r += distanceRatingModifier(h.bestDist, raceDist, h.spread);
        r += getGoingModifier(h.goingPref, going);
        r = r * fitnessModifier(h.rest);
        r += h.wins * 3;
        return { ...h, raceRating: Math.max(1, Math.round(r * 10) / 10) };
    });
}

// ── NEW SEASON ────────────────────────────────────────────────────────────────
function newSeason() {
    const goingOpts = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    raceData.goings = Array.from({ length: 20 }, () => goingOpts[Math.floor(Math.random() * goingOpts.length)]);
    playerData.forEach(p => {
        if (!p.seasonHistory) p.seasonHistory = [];
        p.seasonHistory.push({ season: currentSeason - 1, wins: p.wins, winnings: p.winnings, entries: p.entries, total: p.total });
    });
    const champ = [...playerData].sort((a, b) => (b.total || 0) - (a.total || 0))[0];
    raceData._lastChampion = champ?.name || null;
    raceData._lastChampionSeason = currentSeason - 1;
    incrementHorseAge(horseData);
    const retiring = horseData.filter(h => h.age >= 11);
    const staying = horseData.filter(h => h.age < 11);
    retiring.forEach(h => { h.retired = true; h.retiredSeason = currentSeason - 1; });
    addRetiredHorses(retiring);
    const replacements = [];
    for (const r of retiring) {
        const nh = horsePool.length > 0 ? horsePool.shift() : generateFreshHorse(raceData.horsenames, staying.length + replacements.length);
        Object.assign(nh, { age: 2, rest: 2, runs: 0, wins: 0, money: 0, form: "", history: [], retired: false, owner: r.owner });
        replacements.push(nh);
    }
    staying.forEach(h => { if (h.form) h.form += "/"; });
    setHorseData([...staying, ...replacements]);
    raceData._retirementNotices = retiring.map(h => `${h.name} (${h.owner || '?'}, ${h.runs} runs, £${(h.money || 0).toLocaleString()})`);
    raceData._newHorseNotices = replacements.map(h => `${h.name} (${h.owner || '?'})`);
}

function generateFreshHorse(namePool, index) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random(); while (v === 0) v = Math.random();
    const rating = Math.max(70, Math.min(150, Math.round(110 + 15 * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v))));
    const bd = Math.floor(Math.random() * 28) + 5;
    const sp = bd <= 8 ? parseFloat((1.0 + Math.random() * 1.5).toFixed(2)) : bd <= 14 ? parseFloat((2.0 + Math.random() * 2.0).toFixed(2)) : parseFloat((3.0 + Math.random() * 3.0).toFixed(2));
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    return {
        number: index + 1, name: (namePool?.length) ? namePool[index % namePool.length] : `Yearling ${index + 1}`,
        owner: null, baseRating: rating, rating, bestDist: bd, spread: sp,
        goingPref: goings[Math.floor(Math.random() * goings.length)],
        age: 2, rest: 2, runs: 0, wins: 0, money: 0, form: "", history: [], grade1s: {}, retired: false
    };
}
