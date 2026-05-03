import {
    raceEntries, playerData, horseData, horsePool, raceData, retiredHorses,
    setRaceEntries, setHorseData, incrementHorseRest, resetHorseRest,
    incrementHorseAge, fitnessModifier, convertFractionalOddsToDecimal,
    addRetiredHorses, currentSeason, STABLE_COLOURS
} from './gameState.js';
import {
    canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries
} from './entry.js';
import {
    lineups, raceTime, meeting_number, incrementMeetingNumber, resetMeetingNumber,
    displayGameState, showHistoryModal, showSeasonSummary
} from './horseracing.js';
import { shuffleArray, adjustRatingByAge } from './initialise.js';

// ── RACE STATE ────────────────────────────────────────────────────────────────
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
let currentBets = [];
let humanBetPending = false;
let bettingQueue = [];    // human players still to bet this race
let currentBetPlayer = null;  // human player whose turn it is

const racecardBody = document.getElementById("racecard-body");
const racecardHeader = document.getElementById("racecard-header");
const startBtn = document.getElementById('start-race');
const nextRaceBtn = document.getElementById('next-race');

// ── STABLE COLOURS — imported from gameState.js (single source of truth) ──────

function playerColour(player) {
    if (!player) return STABLE_COLOURS[0];
    const idx = (player.colourIndex ?? 0) % STABLE_COLOURS.length;
    return STABLE_COLOURS[idx];
}
function getPlayerColour(trainerName) {
    // Primary: look up by name in playerData
    const p = playerData.find(p => p.name === trainerName);
    if (p) return playerColour(p);
    // Fallback: derive a consistent colour from the name string itself
    // so at least different trainers get different colours even if playerData isn't ready
    let hash = 0;
    for (let i = 0; i < trainerName.length; i++) hash = trainerName.charCodeAt(i) + ((hash << 5) - hash);
    return STABLE_COLOURS[Math.abs(hash) % STABLE_COLOURS.length];
}
function trainerPill(trainerName) {
    const c = getPlayerColour(trainerName);
    return `<span class="trainer-pill" style="background:${c.bg}">${trainerName}</span>`;
}
function fitnessDot(rest) {
    const colour = rest <= -1 ? '#c0392b' : rest === 0 ? '#e67e22'
        : rest === 1 ? '#f1c40f' : rest === 2 ? '#27ae60'
            : rest === 3 ? '#1abc9c' : '#7f8c8d';
    const title = rest <= -1 ? 'Just ran' : rest === 0 ? 'One rest'
        : rest === 1 ? 'Two rests' : rest === 2 ? 'Fresh'
            : rest === 3 ? 'Very fresh' : 'Long layoff';
    return `<span class="fitness-dot" style="background:${colour}" title="${title}"></span>`;
}

// ── PLACE TERMS ───────────────────────────────────────────────────────────────
const PLACE_TERMS = [
    { minRunners: 2, places: 1, fraction: 1 },
    { minRunners: 5, places: 2, fraction: 4 },
    { minRunners: 8, places: 3, fraction: 5 },
    { minRunners: 12, places: 4, fraction: 4 },
];
function getPlaceTerms(n) {
    let t = PLACE_TERMS[0];
    for (const term of PLACE_TERMS) { if (n >= term.minRunners) t = term; }
    return t;
}

// ── RACE CLASS ELIGIBILITY ────────────────────────────────────────────────────
function filterByClass(raceClass, horseList) {
    const cls = Number(raceClass);
    if (!cls || cls >= 3) return horseList;
    const eligible = horseList.filter(horse => {
        if (!horse.history?.length) return cls >= 4;
        if (cls === 1) return horse.wins > 0;
        if (cls === 2) return horse.history.filter(r => r.position > 0 && r.position <= 3).length >= 2;
        return true;
    });
    return eligible.length >= 4 ? eligible : horseList;
}

// ── START BUTTON ──────────────────────────────────────────────────────────────
startBtn.addEventListener('click', () => {
    bettingQueue = [];
    currentBetPlayer = null;
    humanBetPending = false;
    clearBettingHighlight();
    updateBettingStatus('');
    document.getElementById('race-screen').classList.remove('betting-active');
    startBtn.disabled = true;
    const result = simulateRace(currentRatedHorses);
    displayResults(result);
});

// ── SHOW RACECARD ─────────────────────────────────────────────────────────────
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

    const allRaceHorses = entries
        .map(e => horseData.find(h => h.name === e.horseName))
        .filter(Boolean);
    const eligibleHorses = filterByClass(rGrade, allRaceHorses);

    const ratedHorses = getHorseRatings(eligibleHorses);
    priceHorses = assignFormOdds(ratedHorses, rDist);

    const drawNumbers = shuffleArray([...Array(entries.length)].map((_, i) => i + 1));

    const racecardData = entries.map((entry, i) => {
        const horse = horseData.find(h => h.name === entry.horseName);
        if (!horse) return null;
        const pricedHorse = priceHorses.find(h => h.name === horse.name);
        if (!pricedHorse) return null;
        return {
            draw: drawNumbers[i], horseName: horse.name, age: horse.age,
            trainer: entry.trainer, form: horse.form,
            odds: pricedHorse.odds,
            oddsValue: convertFractionalOddsToDecimal(pricedHorse.odds),
            rest: horse.rest
        };
    }).filter(Boolean).sort((a, b) => a.oddsValue - b.oddsValue);

    const placeTerms = getPlaceTerms(entries.length);
    const placeDesc = entries.length < 5
        ? 'Win only (fewer than 5 runners)'
        : `${placeTerms.places} places at 1/${placeTerms.fraction} odds`;
    const ptEl = document.getElementById('place-terms');
    if (ptEl) ptEl.innerHTML =
        `<small>Class ${rGrade || '?'} &nbsp;·&nbsp; Each Way: ${placeDesc}</small>`;

    racecardHeader.innerHTML = `
        <tr>
            <th>No.</th><th>Horse</th><th>Trainer</th><th>Fit</th>
            <th>Form</th><th>Odds</th><th>Bet</th>
        </tr>`;

    racecardData.forEach(runner => {
        const oddsClass = runner.oddsValue <= 2 ? 'odds-fav'
            : runner.oddsValue <= 8 ? 'odds-mid'
                : 'odds-out';
        racecardBody.innerHTML += `
            <tr class="bet-row" data-horse="${runner.horseName}" data-odds="${runner.odds}"
                style="cursor:pointer" title="Click to bet on ${runner.horseName}">
                <td>${runner.draw}</td>
                <td class="text-start">${runner.horseName}
                    <span class="text-body-secondary small-font">(${runner.age})</span></td>
                <td>${trainerPill(runner.trainer)}</td>
                <td class="text-center">${fitnessDot(runner.rest)}</td>
                <td><a href="#" class="form-link"
                    data-horse-name="${runner.horseName}">${formatFormBadges(runner.form)}</a></td>
                <td class="${oddsClass}">${runner.odds}</td>
                <td class="bet-cell" id="betcell-${runner.horseName.replace(/\s+/g, '_')}">—</td>
            </tr>`;
    });

    currentRatedHorses = ratedHorses;
    currentBets = [];

    document.querySelectorAll('.form-link').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            showHistoryModal(this.getAttribute('data-horse-name'));
        });
    });

    nextRaceBtn.disabled = true;
    startBtn.disabled = false;
    startBettingRound();
}

// ── BETTING ROUND ─────────────────────────────────────────────────────────────
function startBettingRound() {
    for (const player of playerData) {
        if (!player.human) {
            const bet = computerPlaceBet(player);
            if (bet) recordBet(bet);
        }
    }

    const MIN_BET = 10;
    const brokeHumans = playerData.filter(p => p.human && (p.total || 0) < MIN_BET);
    bettingQueue = playerData.filter(p => p.human && (p.total || 0) >= MIN_BET);

    renderBetsTable();
    advanceBettingQueue();
}

function advanceBettingQueue() {
    clearBettingHighlight();

    if (bettingQueue.length === 0) {
        currentBetPlayer = null;
        humanBetPending = false;
        document.getElementById('race-screen').classList.remove('betting-active');
        const anyHumans = playerData.some(p => p.human);
        updateBettingStatus(anyHumans
            ? `All bets in — click <strong>▶ Start Race</strong> when ready.` : '');
        return;
    }

    currentBetPlayer = bettingQueue.shift();
    humanBetPending = true;

    const colour = playerColour(currentBetPlayer);
    highlightBettingRows(colour.bg);
    document.getElementById('race-screen').classList.add('betting-active');

    const remaining = bettingQueue.length;
    const afterNote = remaining > 0
        ? ` &nbsp;<span class="text-warning" style="font-size:0.75rem">`
        + `(${remaining} player${remaining > 1 ? 's' : ''} to follow)</span>` : '';

    updateBettingStatus(`
        <span style="display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span class="trainer-pill" style="background:${colour.bg};font-size:0.82rem">
                ${currentBetPlayer.name}
            </span>
            — click a horse to bet${afterNote}
            &nbsp;·&nbsp;
            <button id="skip-bet-btn" class="btn btn-sm btn-outline-light py-0 px-2"
                style="font-size:0.75rem;border-color:rgba(255,255,255,0.5)">
                Skip my bet →
            </button>
        </span>`);

    const skipBtn = document.getElementById('skip-bet-btn');
    if (skipBtn) skipBtn.onclick = () => advanceBettingQueue();
}

function highlightBettingRows(hexColour) {
    const r = parseInt(hexColour.slice(1, 3), 16);
    const g = parseInt(hexColour.slice(3, 5), 16);
    const b = parseInt(hexColour.slice(5, 7), 16);
    const tint = `rgba(${r},${g},${b},0.13)`;
    document.querySelectorAll('.bet-row').forEach(row => {
        row.style.backgroundColor = tint;
        row.style.cursor = 'pointer';
        row._betHandler = onBetRowClick.bind(row);
        row.addEventListener('click', row._betHandler);
    });
}

function clearBettingHighlight() {
    document.querySelectorAll('.bet-row').forEach(row => {
        row.style.backgroundColor = '';
        row.style.cursor = '';
        if (row._betHandler) {
            row.removeEventListener('click', row._betHandler);
            delete row._betHandler;
        }
    });
}

function onBetRowClick(e) {
    if (e.target.classList.contains('form-link')) return;
    if (!humanBetPending || !currentBetPlayer) return;
    openBetModal(this.getAttribute('data-horse'), this.getAttribute('data-odds'));
}

function updateBettingStatus(msg) {
    const el = document.getElementById('betting-status');
    if (el) el.innerHTML = msg;
}

// ── COMPUTER BETTING ──────────────────────────────────────────────────────────
function computerPlaceBet(player) {
    const profile = player.bettingProfile || 'cautious';
    const balance = player.total || 0;
    if (balance < 10) return null;

    const rand = Math.random();
    const runners = [...priceHorses].sort((a, b) =>
        convertFractionalOddsToDecimal(a.odds) - convertFractionalOddsToDecimal(b.odds));
    if (!runners.length) return null;

    const favourite = runners[0];
    const outsiders = runners.filter(h => convertFractionalOddsToDecimal(h.odds) >= 5);
    const ownHorses = priceHorses.filter(h =>
        entries.some(e => e.horseName === h.name && e.trainer === player.name));

    let chosen = null, betType = 'win', balanceFraction = 0;

    switch (profile) {
        case 'favourite_backer':
            if (rand < 0.80) {
                chosen = favourite; betType = 'win';
                balanceFraction = 0.03 + rand * 0.05;
            }
            break;
        case 'outsider':
            if (outsiders.length && rand < 0.70) {
                chosen = outsiders[Math.floor(Math.random() * outsiders.length)];
                betType = rand < 0.55 ? 'ew' : 'win';
                balanceFraction = 0.01 + rand * 0.03;
            }
            break;
        case 'each_way':
            chosen = runners[Math.floor(Math.random() * Math.min(5, runners.length))];
            betType = 'ew';
            balanceFraction = 0.01 + rand * 0.03;
            break;
        case 'high_risk':
            if (outsiders.length) {
                chosen = outsiders[Math.floor(Math.random() * outsiders.length)];
                betType = rand < 0.25 ? 'ew' : 'win';
                balanceFraction = 0.06 + rand * 0.10;
            }
            break;
        case 'form_follower': {
            const byWins = entries.map(e => horseData.find(h => h.name === e.horseName))
                .filter(Boolean).sort((a, b) => (b.wins || 0) - (a.wins || 0));
            if (byWins.length && rand < 0.70) {
                chosen = priceHorses.find(h => h.name === byWins[0].name);
                betType = rand < 0.45 ? 'ew' : 'win';
                balanceFraction = 0.02 + rand * 0.04;
            }
            break;
        }
        case 'own_horse':
            if (ownHorses.length && rand < 0.85) {
                chosen = ownHorses[Math.floor(Math.random() * ownHorses.length)];
                betType = rand < 0.50 ? 'ew' : 'win';
                balanceFraction = 0.02 + rand * 0.05;
            } else if (rand < 0.35) {
                chosen = favourite; betType = 'win';
                balanceFraction = 0.01 + rand * 0.02;
            }
            break;
        case 'cautious':
        default:
            if (rand < 0.45) {
                chosen = runners[Math.floor(Math.random() * Math.min(3, runners.length))];
                betType = rand < 0.35 ? 'ew' : 'win';
                balanceFraction = 0.005 + rand * 0.015;
            }
            break;
    }

    if (!chosen || balanceFraction <= 0) return null;

    let stake = Math.round((balance * balanceFraction) / 10) * 10;
    stake = Math.max(10, Math.min(stake, balance));
    if (betType === 'ew' && stake * 2 > balance) stake = Math.floor(balance / 20) * 10;
    if (stake < 10) return null;

    const { potentialWin, potentialPlace } = calcReturns(chosen.odds, stake, betType, entries.length);
    return {
        playerName: player.name, horseName: chosen.name, type: betType,
        stake, potentialWin, potentialPlace, odds: chosen.odds
    };
}

// ── HUMAN BET MODAL ───────────────────────────────────────────────────────────
function openBetModal(horseName, odds) {
    const human = currentBetPlayer;
    if (!human) return;
    if ((human.total || 0) < 10) { advanceBettingQueue(); return; }

    const placeTerms = getPlaceTerms(entries.length);
    const maxStake = Math.min(rPrizes[0], human.total || 0);
    const ewAvail = entries.length >= 5;
    const colour = playerColour(human);

    const modalHeader = document.querySelector('#betModal .modal-header');
    if (modalHeader) modalHeader.style.background = colour.bg;

    document.getElementById('betModalLabel').textContent = `${human.name} — Place a Bet`;
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

    const ewRadio = document.getElementById('bet-type-ew');
    if (ewRadio) ewRadio.disabled = !ewAvail;
    document.getElementById('bet-type-win').checked = true;

    const updatePotential = () => {
        const stake = parseFloat(document.getElementById('bet-stake').value) || 0;
        const betType = document.getElementById('bet-type').value;
        if (stake <= 0) { document.getElementById('bet-potential').innerHTML = ''; return; }
        const { potentialWin, potentialPlace } = calcReturns(odds, stake, betType, entries.length);
        document.getElementById('bet-potential').innerHTML = betType === 'win'
            ? `If wins: <strong class="text-success">£${potentialWin.toLocaleString()}</strong>`
            : `If wins: <strong class="text-success">£${potentialWin.toLocaleString()}</strong>
               &nbsp;|&nbsp; If places:
               <strong class="text-primary">£${potentialPlace.toLocaleString()}</strong>
               <br><small class="text-muted">Two bets of £${stake}
               = £${(stake * 2).toLocaleString()} total</small>`;
    };

    document.getElementById('bet-stake').oninput = updatePotential;
    document.getElementById('bet-type').onchange = updatePotential;
    buildQuickStakes(maxStake);

    document.getElementById('bet-confirm').onclick = () => {
        const stake = parseFloat(document.getElementById('bet-stake').value) || 0;
        const betType = document.getElementById('bet-type').value;
        const totalStake = betType === 'ew' ? stake * 2 : stake;
        const errEl = document.getElementById('bet-error');
        if (stake <= 0) { errEl.textContent = 'Enter a valid stake.'; return; }
        if (stake > rPrizes[0]) { errEl.textContent = `Max stake: £${rPrizes[0].toLocaleString()}.`; return; }
        if (totalStake > (human.total || 0)) { errEl.textContent = 'Insufficient funds.'; return; }

        errEl.textContent = '';
        const { potentialWin, potentialPlace } = calcReturns(odds, stake, betType, entries.length);
        recordBet({
            playerName: human.name, horseName, type: betType,
            stake, potentialWin, potentialPlace, odds
        });
        updateBetCell(horseName, betType, stake);
        bootstrap.Modal.getInstance(document.getElementById('betModal')).hide();
        renderBetsTable();
        advanceBettingQueue();
    };

    const cancelBtn = document.querySelector('#betModal .btn-outline-secondary');
    if (cancelBtn) {
        cancelBtn.onclick = () => {
            bootstrap.Modal.getInstance(document.getElementById('betModal'))?.hide();
            advanceBettingQueue();
        };
    }

    new bootstrap.Modal(document.getElementById('betModal')).show();
}

// ── BET HELPERS ───────────────────────────────────────────────────────────────
function calcReturns(oddsStr, stake, betType, numRunners) {
    const [num, denom] = oddsStr.split('/').map(Number);
    const winReturn = Math.round(stake * (num / denom) + stake);
    const terms = getPlaceTerms(numRunners);
    const placeReturn = Math.round(stake * (num / denom / terms.fraction) + stake);
    return betType === 'win'
        ? { potentialWin: winReturn, potentialPlace: 0 }
        : { potentialWin: winReturn + placeReturn, potentialPlace: placeReturn };
}

function recordBet(bet) {
    currentBets = currentBets.filter(b => b.playerName !== bet.playerName);
    currentBets.push(bet);
}

function updateBetCell(horseName, betType, stake) {
    const cell = document.getElementById(`betcell-${horseName.replace(/\s+/g, '_')}`);
    if (!cell) return;
    cell.innerHTML =
        `<span class="bet-placed-badge">${betType === 'ew' ? 'E/W' : 'Win'} £${stake}</span>`;
}

function renderBetsTable() {
    const tbody = document.getElementById('bets-body');
    if (!tbody) return;
    if (!currentBets.length) {
        tbody.innerHTML =
            `<tr><td colspan="7" class="text-muted text-center small">No bets placed</td></tr>`;
        return;
    }
    tbody.innerHTML = currentBets.map(b => {
        const stakeStr = b.type === 'ew'
            ? `£${b.stake.toLocaleString()} ×2` : `£${b.stake.toLocaleString()}`;
        const retStr = b.type === 'ew'
            ? `£${b.potentialWin.toLocaleString()} / £${b.potentialPlace.toLocaleString()}`
            : `£${b.potentialWin.toLocaleString()}`;
        const resultHtml = b.result
            ? `<span class="${b.won ? 'text-success fw-bold' : 'text-danger'}">${b.result}</span>`
            : '—';
        return `<tr>
            <td>${trainerPill(b.playerName)}</td>
            <td>${b.horseName}</td>
            <td>${b.odds}</td>
            <td>${b.type === 'ew' ? 'E/W' : 'Win'}</td>
            <td>${stakeStr}</td>
            <td>${retStr}</td>
            <td>${resultHtml}</td>
        </tr>`;
    }).join('');
}

function buildQuickStakes(maxStake) {
    const el = document.getElementById('quick-stakes');
    if (!el) return;
    const amounts = [10, 50, 100, 250, 500, 1000].filter(a => a <= maxStake);
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

// ── SETTLE BETS ───────────────────────────────────────────────────────────────
function settleBets(finishingOrder) {
    const terms = getPlaceTerms(entries.length);
    const placedNames = finishingOrder.slice(0, terms.places).map(h => h.name);
    const winner = finishingOrder[0]?.name;

    currentBets.forEach(bet => {
        const pi = playerData.findIndex(p => p.name === bet.playerName);
        if (pi === -1) return;
        const player = playerData[pi];
        const totalOut = bet.type === 'ew' ? bet.stake * 2 : bet.stake;
        player.betStaked = (player.betStaked || 0) + totalOut;
        player.betReturned = (player.betReturned || 0);

        let payout = 0;
        if (bet.type === 'win') {
            if (bet.horseName === winner) payout = bet.potentialWin;
        } else {
            if (bet.horseName === winner) payout += bet.potentialWin;
            else if (placedNames.includes(bet.horseName)) payout += bet.potentialPlace;
        }
        player.betReturned = (player.betReturned || 0) + payout;
        player.total = (player.total || 0) + (payout - totalOut);

        bet.result = (payout - totalOut) >= 0
            ? `+£${payout.toLocaleString()}` : `-£${totalOut.toLocaleString()}`;
        bet.won = payout > 0;
        playerData[pi] = player;
    });
}

// ── RACE SIMULATION WITH INCIDENTS ───────────────────────────────────────────
function simulateRace(horses) {
    const maxVar = Math.max(...horses.map(h => h.raceRating)) / 10;
    return horses.map(horse => {
        let score = horse.raceRating
            + Math.random() * maxVar * (Math.random() < 0.5 ? -1 : 1);
        const incident = Math.random();
        if (incident < 0.03) {
            score -= (3 + Math.random() * 8);
            horse._incident = 'hampered';
        } else if (incident < 0.05) {
            score += ((horse.raceRating < 90 ? 15 : 8) + Math.random() * 10);
            horse._incident = 'bolted up';
        }
        return { ...horse, finalScore: score };
    }).sort((a, b) => b.finalScore - a.finalScore);
}

// ── DISPLAY RESULTS ───────────────────────────────────────────────────────────
function displayResults(finishingOrder) {
    racecardHeader.innerHTML = `
        <tr>
            <th>Pos.</th><th>Horse</th><th>Trainer</th>
            <th>Odds</th><th>Prize</th><th>Note</th>
        </tr>`;
    racecardBody.innerHTML = "";
    const medals = ['🥇', '🥈', '🥉'];

    finishingOrder.forEach((horse, i) => {
        const odds = priceHorses.find(h => h.name === horse.name)?.odds || "?";
        const prize = i < 3 ? `£${rPrizes[i].toLocaleString()}` : "";
        const rowClass = i === 0 ? 'result-1st'
            : i === 1 ? 'result-2nd'
                : i === 2 ? 'result-3rd' : '';
        const incident = horse._incident
            ? `<span class="badge bg-warning text-dark">${horse._incident}</span>` : '';
        racecardBody.innerHTML += `
            <tr class="${rowClass}">
                <td>${medals[i] || ''} ${i + 1}</td>
                <td class="text-start fw-bold">${horse.name}</td>
                <td>${trainerPill(horse.owner || '?')}</td>
                <td>${odds}</td>
                <td class="text-success fw-bold">${prize}</td>
                <td>${incident}</td>
            </tr>`;
    });

    updateHorseData(finishingOrder, raceData.raceclass[gameRaceNumber]);
    updatePlayerData(finishingOrder);
    settleBets(finishingOrder);
    renderBetsTable();

    if (window.HoF) window.HoF.load(horseData, retiredHorses, currentSeason);
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
        if (pos === 1 && Number(grade) === 1) h.grade1s[rDist] = (h.grade1s[rDist] || 0) + 1;
        h.rest = -1;
        h.runs = (h.runs || 0) + 1;

        const pm = i < 3 ? (Number(rPrizes[i]) || 0) : 0;
        h.money = (h.money || 0) + pm;

        h.history = h.history || [];
        h.history.push({
            season: currentSeason,
            meeting: meeting_number + 1,
            course: rCourse,
            name: rName,
            going: curGoing,
            distance: rDist,
            position: pos,
            winnings: pm,
            racePrize: rPrize   // ← stored so entry.js can weight result quality
        });

        horseData[hi] = h;
    });

    startBtn.disabled = true;
    nextRaceBtn.disabled = false;
}

// ── UPDATE PLAYER DATA ────────────────────────────────────────────────────────
function updatePlayerData(results) {
    // Entry fee per horse entered (from lineup, not results)
    const fee = rPrize * 0.1;
    entries.forEach(entry => {
        const pi = playerData.findIndex(p => p.name === entry.trainer);
        if (pi === -1) return;
        playerData[pi].entries = (playerData[pi].entries || 0) + fee;
        playerData[pi].total = (playerData[pi].total || 0) - fee;
    });

    // Prize money for top 3
    results.forEach((horse, i) => {
        const pi = playerData.findIndex(p => p.name === horse.owner);
        if (pi === -1) return;
        if (i === 0) playerData[pi].wins = (playerData[pi].wins || 0) + 1;
        const prize = i < 3 ? Number(rPrizes[i]) : 0;
        if (prize > 0) {
            playerData[pi].prizeWinnings = (playerData[pi].prizeWinnings || 0) + prize;
            playerData[pi].total = (playerData[pi].total || 0) + prize;
        }
    });
}

// ── NEXT RACE ─────────────────────────────────────────────────────────────────
document.getElementById('next-race').addEventListener('click', handleNextRace);

function handleNextRace() {
    meetingRaceNumber++;
    if (meetingRaceNumber === 6) {
        nextRaceBtn.textContent = "Next Race";
        startBtn.disabled = true;
        nextRaceBtn.disabled = false;
        handleContinueToNextMeeting();
        return;
    }
    nextRaceBtn.textContent = meetingRaceNumber === 5 ? "Continue" : "Next Race";
    showRacecard(meetingRaceNumber);
    startBtn.disabled = false;
    nextRaceBtn.disabled = true;
}

function handleContinueToNextMeeting() {
    incrementHorseRest(horseData);
    meetingRaceNumber = 0;
    const isLast = meeting_number >= raceData.meetings.length - 1;

    if (!isLast) {
        incrementMeetingNumber();
        nextRaceBtn.textContent = "Next Race";
        nextRaceBtn.disabled = true;
        startBtn.disabled = true;
        displayGameState();
    } else {
        resetMeetingNumber();   // increments currentSeason, resets meeting to 0
        showSeasonSummary(playerData, horseData, currentSeason - 1, () => {
            newSeason();
            resetHorseRest(horseData);
            displayGameState();
        });
    }
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
const commonOddsWithProb = commonFractionalOdds.map(([n, d]) =>
    ({ n, d, impliedProb: d / (n + d) }));

function distanceToFurlongs(s) {
    if (!s) return 0;
    if (/^\d+f$/.test(s)) return parseInt(s);
    const m = s.match(/^(\d+)m(?:(\d+)f)?$/);
    if (!m) return 0;
    return parseInt(m[1]) * 8 + (m[2] ? parseInt(m[2]) : 0);
}

function assignFormOdds(raceHorses, targetDist) {
    const td = distanceToFurlongs(targetDist);
    const scores = raceHorses.map(h => {
        let s = h.history?.length ? 0 : 5;
        for (const r of (h.history || [])) {
            const dd = Math.abs(distanceToFurlongs(r.distance) - td);
            const dw = Math.max(0, 1 - dd / 10);
            if (!isNaN(r.position) && r.position > 0)
                s += Math.max(0, 10 - r.position) * dw;
        }
        if (h.age === 4) s += 1;
        else if (h.age === 5) s += 2;
        else if (h.age >= 6 && h.age <= 8) s += 3;
        else if (h.age === 9) s += 1;
        else if (h.age === 10) s += 0.5;
        if (h.rest === 2) s += 3;
        else if (h.rest === 1) s += 1;
        else if (h.rest > 2) s += 1;
        return { horse: h, score: s };
    });
    const total = scores.reduce((a, x) => a + x.score, 0) || 1;
    const over = 1 + Math.random() * 0.13 + 0.02;
    return scores.map(({ horse, score }) => {
        const p = Math.min(score / total * over, 1);
        const best = commonOddsWithProb.reduce((c, o) =>
            Math.abs(o.impliedProb - p) < c.diff ? { ...o, diff: Math.abs(o.impliedProb - p) } : c,
            { diff: Infinity });
        return { name: horse.name, odds: `${best.n}/${best.d}`, impliedProb: p };
    });
}

function distanceRatingModifier(bestDist, raceDist, spread) {
    const diff = raceDist - bestDist;
    if (Math.abs(diff) <= spread) return 0;
    const excess = Math.abs(diff) - spread;
    return -(Math.pow(excess, 1.7) * 1.3 * (diff < 0 ? 1.5 : 1.0));
}

function getGoingModifier(pref, actual) {
    const opts = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    return -Math.abs(opts.indexOf(pref) - opts.indexOf(actual)) * 1.5;
}

function getHorseRatings(raceHorses) {
    const raceDist = distanceToFurlongs(rDist);
    return raceHorses.map(h => {
        let r = h.rating;
        r += distanceRatingModifier(h.bestDist, raceDist, h.spread);
        r += getGoingModifier(h.goingPref, rGoing);
        r = r * fitnessModifier(h.rest);
        r += h.wins * 3;
        return { ...h, raceRating: Math.max(1, Math.round(r * 10) / 10) };
    });
}

// ── FORM BADGE HELPERS ────────────────────────────────────────────────────────
function formatFormBadges(formStr) {
    if (!formStr) return '—';
    return formStr.split('').map(ch => {
        if (ch === '/') return `<span class="form-sep">/</span>`;
        const cls = ch === '1' ? 'form-1' : ch === '2' ? 'form-2' : ch === '3' ? 'form-3'
            : ch === '0' ? 'form-0' : ['4', '5', '6'].includes(ch) ? 'form-4' : 'form-7';
        return `<span class="form-badge ${cls}">${ch}</span>`;
    }).join('');
}

// ── NEW SEASON ────────────────────────────────────────────────────────────────
function newSeason() {
    const goingOpts = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    raceData.goings = Array.from({ length: 20 }, () =>
        goingOpts[Math.floor(Math.random() * goingOpts.length)]);

    playerData.forEach(p => {
        if (!p.seasonHistory) p.seasonHistory = [];
        p.seasonHistory.push({
            season: currentSeason - 1,
            wins: p.wins,
            prizeWinnings: p.prizeWinnings || 0,
            betStaked: p.betStaked || 0,
            betReturned: p.betReturned || 0,
            entries: p.entries || 0,
            total: p.total || 0
        });
    });

    const champ = [...playerData].sort((a, b) => (b.total || 0) - (a.total || 0))[0];
    raceData._lastChampion = champ?.name || null;
    raceData._lastChampionSeason = currentSeason - 1;

    incrementHorseAge(horseData);

    const retiring = horseData.filter(h => h.age >= 11);
    const staying = horseData.filter(h => h.age < 11);

    retiring.forEach(h => { h.retired = true; h.retiredSeason = currentSeason - 1; });
    addRetiredHorses(retiring);

    const poolNames = raceData.horsenames ? raceData.horsenames.slice(144) : [];
    const replacements = [];
    for (const r of retiring) {
        const nh = horsePool.length > 0
            ? horsePool.shift()
            : generateFreshHorse(poolNames, replacements.length);
        Object.assign(nh, {
            age: 4, rest: 2, runs: 0, wins: 0, money: 0,
            form: "", history: [], retired: false, owner: r.owner
        });
        nh.rating = adjustRatingByAge(nh.baseRating, 4);
        replacements.push(nh);
    }

    staying.forEach(h => { if (h.form) h.form += "/"; });
    setHorseData([...staying, ...replacements]);

    raceData._retirementNotices = retiring.map(h =>
        `${h.name} (${h.owner || '?'}, ${h.runs} runs, £${(h.money || 0).toLocaleString()})`);
    raceData._newHorseNotices = replacements.map(h => `${h.name} (${h.owner || '?'})`);

    if (window.HoF) window.HoF.load(horseData, retiredHorses, currentSeason);
}

function generateFreshHorse(namePool, index) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    const base = Math.max(70, Math.min(150,
        Math.round(110 + 15 * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v))));
    const bd = Math.floor(Math.random() * 28) + 5;
    const sp = bd <= 8 ? parseFloat((1.0 + Math.random() * 1.5).toFixed(2))
        : bd <= 14 ? parseFloat((2.0 + Math.random() * 2.0).toFixed(2))
            : parseFloat((3.0 + Math.random() * 3.0).toFixed(2));
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    return {
        number: index + 1,
        name: (namePool?.length) ? namePool[index % namePool.length] : `Recruit ${index + 1}`,
        owner: null,
        baseRating: base,
        rating: base,
        bestDist: bd,
        spread: sp,
        goingPref: goings[Math.floor(Math.random() * goings.length)],
        age: 4, rest: 2, runs: 0, wins: 0, money: 0, form: "", history: [], grade1s: {}, retired: false
    };
}
