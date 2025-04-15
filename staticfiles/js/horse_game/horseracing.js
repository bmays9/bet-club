import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';


let meeting_number = 0;
let raceTime = ["1:15", "1:50", "2:25", "3:00", "3:35", "4:10"]
let players = []
const TOTALHORSES = 144
let raceData = {}; // Declare raceData globally
let playerData = {};
let horseData = {};
let raceEntries = {};
let going = ["Soft-Ish", "Sofyt"];


async function getRaceData() {
    raceData = await fetchTextFiles();
    console.log("Race data in another file:", raceData);
    
    // Example usage
    console.log("Horsenames:", raceData.horsenames);
    shuffleArray(raceData.horsenames); // Shuffle the array
    raceData.horsenames = raceData.horsenames.slice(0, TOTALHORSES) // only need 6 * 24
    console.log("Horsenames:", raceData.horsenames);

}

function shuffleArray(array) {
    for (let i = array.length -1; i > 0 ; i--) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
}


function getRandomGoingPreference() {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    const weights = [5, 15, 40, 25, 15]; // Must match order of goings

    const totalWeight = weights.reduce((sum, w) => sum + w, 0);
    const rand = Math.random() * totalWeight;

    let cumulative = 0;
    for (let i = 0; i < goings.length; i++) {
        cumulative += weights[i];
        if (rand < cumulative) return goings[i];
    }

    return goings[goings.length - 1]; // Fallback
}

function horseRating(distance, peakDistance, maxRating, spread) {
    const exponent = -Math.pow(distance - peakDistance, 2) / (2 * Math.pow(spread, 2));
    return maxRating * Math.exp(exponent);
}

function setPlayerData(playersList) {
    
    let plyr = [];
    let wins = 0;
    let betting = 0;
    let entries = 0;
    let winnings = 0;
    let total = 0;

    for (let i = 0; i < playersList.length; i++){
        let player = playersList[i]
        
        plyr.push({
            name: player.name,
            wins,
            betting,
            entries,
            winnings,
            total
        })
    }
    
    return plyr
}

function buildHorseData() {
    
    let horses = [];
    console.log("players:", players);
    console.log("playerData:", playerData);

    for (let i = 0; i < TOTALHORSES; i++) {
        let rating = Math.floor(Math.random() * 101) + 10; // 10 to 110
        const bestDist = Math.floor(Math.random() * 28) + 5;  // 5 to 32
        const spread = parseFloat((Math.random() * 8 + 2).toFixed(2)); // 2.00 to 10.00
        let age = Math.floor(Math.random() * 7 + 4);
        let rest = 0
        const goingPref = getRandomGoingPreference();
        const name = raceData.horsenames[i];
        // Assign owner in chunks of 24
        const ownerIndex = Math.floor(i / 24);
        const owner = playerData[ownerIndex].name || `Unknown`;
        let number = i + 1
        let runs = 0, wins = 0, money = 0  
        
        horses.push({
            number,
            name,
            owner,
            baseRating: rating,
            rating,
            bestDist,
            spread,
            goingPref,
            age,
            rest,
            runs,
            wins,
            money,
        });
    }

    return horses;
}

function adjustRatingByAge(baseRating, age) {
    let modifier = 1;

    if (age === 4) modifier = 0.90;
    else if (age === 5) modifier = 0.95;
    else if (age >= 6 && age <= 8) modifier = 1.00;
    else if (age === 9) modifier = 0.95;
    else if (age === 10) modifier = 0.90;

    return Math.round(baseRating * modifier);
}

function endOfSeasonUpdate(horses) {
    for (let horse of horses) {
        horse.age++;
        horse.rating = adjustRatingByAge(horse.baseRating, horse.age);
    }
}

function goingModifier(horseGoingPref, raceGoing) {
    const goings = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];

    const prefIndex = goings.indexOf(horseGoingPref);
    const raceIndex = goings.indexOf(raceGoing);

    const distance = Math.abs(prefIndex - raceIndex);

    if (distance === 0) return 1.0;
    if (distance === 1) return 0.95;
    if (distance === 2) return 0.85;
    return 0.75;
}

function displayGameState(array) {

    console.log("Checking raceData:", raceData);
    document.getElementById('gs-meeting').innerHTML = `${raceData.meetings[meeting_number]} (${meeting_number + 1} of ${raceData.meetings.length})`;

    if (!raceData || !raceData.distances) {
        console.error("Race data is not loaded yet.");
        return;
    }
    let tableHtml = "";
    tableHtml = `<tr>
                <th>Time</th>
                <th>Distance</th>
                <th>Name</th>
                <th>Prize Money</th>
                </tr>`;
    
    for (let i = 0; i < 6; i++) {
        tableHtml += 
            `<tr>
            <td>${raceTime[i]}</td>
            <td>${raceData.distances[meeting_number * 6 + i]}</td>
            <td>${raceData.racenames[meeting_number * 6 + i]}</td>
            <td>${raceData.prizemoney[meeting_number * 6 + i]}</td>
            </tr>`;
                }
    
    document.getElementById('gs-meeting-races').innerHTML = tableHtml;

    // Player data
 
    console.log("Player Data", playerData)
    let playerTableHtml = "";
    playerTableHtml = `<tr>
                <th>Pos</th>
                <th>Name</th>
                <th>Wins</th>
                <th>Betting</th>
                <th>Fees</th>
                <th>Winnings</th>
                <th>Total</th>
                </tr>`;
    
    for (let i = 0; i < 6; i++) {
        const player = playerData[i]; // extract player object
        playerTableHtml += 
            `<tr>
            <td>${i + 1}</td>
            <td>${player.name}</td>
            <td>${player.wins}</td>
            <td>£${player.betting}</td>
            <td>£${player.entries}</td>
            <td>£${player.winnings}</td>
            <td>£${player.total}</td>
            </tr>`;
                }
    
    document.getElementById('gs-players').innerHTML = playerTableHtml;

}

document.getElementById('clear-game-state').addEventListener('click', function () {
    // Clear game state tables
    console.log("raceData in clear-game-state click:", raceData);
    document.getElementById('gs-meeting-races').innerHTML = "";
    document.getElementById('gs-players').innerHTML = "";
    document.getElementById('next-meeting').innerHTML = "";
    document.getElementById('gs-standings').innerHTML = "";
    document.getElementById('gs-meeting').innerHTML = `${raceData.meetings[meeting_number]} | Good-Soft`
    document.getElementById('clear-game-state').style.display = 'none';

    // Randomize the Picking Order
    shuffleArray(playerData); // Shuffle the array

    //empty the entries array
    raceEntries = {
        0: [],
        1: [],
        2: [],
        3: [],
        4: [],
        5: []
    };


    displayRaceSelections()
    displayStable(0)

    });

function displayRaceSelections() {
    
    let selectionHtml = "";
    selectionHtml = `<tr>
                <th>Time</th>
                <th>Dist</th>
                <th>#1</th>
                <th>#2</th>
                <th>#3</th>
                </tr>`;
                
    for (let i = 0; i < 6; i++) {
        const distance = raceData.distances[meeting_number * 6 + i] || "—";
                
        const entries = raceEntries[i] || [];
        const selections = [
        entries[0] || "",
        entries[1] || "",
        entries[2] || ""
        ];
                
        selectionHtml += `<tr>
                    <td>${raceTime[i]}</td>
                    <td>${distance}</td>
                    <td>${selections[0]}</td>
                    <td>${selections[1]}</td>
                    <td>${selections[2]}</td>
                    </tr>`;
                }
                
    document.getElementById('race-selection').innerHTML = selectionHtml;
}

function displayStable(currentPlayerIndex) {
    
    const playerName = playerData[currentPlayerIndex].name;

    const playerHorses = horseData.filter(horse => horse.owner === playerName);

    let stableHtml = "";
    stableHtml = `<tr>
                <th>Sel</th>
                <th>Fit</th>
                <th>Name</th>
                <th>R</th>
                <th>W</th>
                <th>Winnings</th>
                <th>Form</th>
                </tr>`;
                
    for (let i = 0; i < playerHorses.length; i++) {
        const horse = playerHorses[i];
                
        stableHtml += `<tr>
                    <td>
                        <input type="radio" class="btn-check horse-select" name="btnradio" id="btnradio${i}" autocomplete="off">
                        <label class="btn btn-sm btn-outline-primary rounded-pill px-2 py-0" for="btnradio${i}">🎯</label>
                    </td>            
                    <td>${horse.rest}</td>            
                    <td>${horse.name}</td>
                    <td>${horse.runs}</td>
                    <td>${horse.wins}</td>
                    <td>£${horse.money}</td>
                    <td>${horse.money}</td>
                    </tr>`;
                }
                
    document.getElementById('st-selection').innerHTML = stableHtml;  
    
}



export async function runHorseRacing(players) {
    
    await getRaceData();
    playerData = setPlayerData(players);
    horseData = buildHorseData();
    displayGameState(meeting_number);
    endOfSeasonUpdate(horseData);
}

