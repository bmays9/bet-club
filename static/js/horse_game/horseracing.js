import { fetchTextFiles } from "./load_data.js";
import { allEntries, canEnterRace, enterHorse, displayRaceEntries } from './entry.js';
import { shuffleArray, getRandomGoingPreference, buildHorseData, adjustRatingByAge, endOfSeasonUpdate, goingModifier, resetPlayerData } from './initialise.js';
import { playerData, horseData, raceData, setHorseData, setPlayerData, setRaceData } from './gameState.js';

let meeting_number = 0;
let raceTime = ["1:15", "1:50", "2:25", "3:00", "3:35", "4:10"]
let players = []
const TOTALHORSES = 144
let going = ["Soft-Ish", "Sofyt"];
let selectedRaceIndex = null;


async function buildRaceData() {
    const data = await fetchTextFiles(); // Fetch the data, store it in a local variable
    console.log("Race data in another file:", data);
    
    // Example usage
    console.log("Horsenames:", data.horsenames);
    shuffleArray(data.horsenames); // Shuffle the array
    data.horsenames = data.horsenames.slice(0, TOTALHORSES); // only need 6 * 24
    console.log("Horsenames after slice:", data.horsenames);
    
    setRaceData(data); // Save the fetched data to the global state via the setter
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
        const player = playerData()[i]; // extract player object
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
    shuffleArray(getPlayerData()); // Shuffle the array

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
        let selectionHtml = `<tr>
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
            
            selectionHtml += `<tr class="race-row ${selectedRaceIndex === i ? 'table-primary' : ''}" data-index="${i}">
                <td>${raceTime[i]}</td>
                <td>${distance}</td>
                <td>${selections[0]}</td>
                <td>${selections[1]}</td>
                <td>${selections[2]}</td>
            </tr>`;
        }
    
        document.getElementById('race-selection').innerHTML = selectionHtml;
    
        // ✅ Add click handlers right after rendering
        document.querySelectorAll('.race-row').forEach(row => {
            row.addEventListener('click', function () {
                selectedRaceIndex = parseInt(this.getAttribute('data-index'));
                displayRaceSelections(); // Re-render to highlight the selected row
            });
        });
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
                
                    // Check if the horse has already been entered into a race
                    let enteredRaceIndex = null;
                    for (let j = 0; j < 6; j++) {
                        if (raceEntries[j].includes(horse.name)) {
                            enteredRaceIndex = j;
                            break;
                        }
                    }
                
                    const entrySymbol = enteredRaceIndex !== null ? `${enteredRaceIndex + 1}` : "➤";
                    const rowClass = enteredRaceIndex !== null ? "table-success" : "";
                
                    stableHtml += `<tr class="${rowClass}">
                        <td>
                            <input type="radio" class="btn-check horse-select" name="btnradio" id="btnradio${i}" autocomplete="off">
                            <label 
                                class="btn btn-sm btn-outline-primary rounded-pill px-0 py-0 horse-entry-btn" 
                                data-horse-name="${horse.name}" 
                                for="btnradio${i}">${entrySymbol}</label>
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
    
    document.querySelectorAll('.horse-entry-btn').forEach(button => {
        button.addEventListener('click', function () {
            if (selectedRaceIndex === null) {
                alert("Please select a race first.");
                return;
            }
    
            const horseName = this.getAttribute('data-horse-name');
            const race = raceEntries[selectedRaceIndex];
    
            if (race.length >= 3) {
                alert("This race already has 3 entries.");
                return;
            }
    
            // Prevent duplicate entries
            if (race.includes(horseName)) {
                alert("This horse is already entered in this race.");
                return;
            }
    
            race.push(horseName);
            displayRaceSelections(); // Update display
        });
    });
}



export async function runHorseRacing(players) {
    await buildRaceData();
    const builtData = resetPlayerData(players); // <-- BUILD playerData
    setPlayerData(builtData);                   // <-- SAVE to shared state

    setHorseData(buildHorseData());             // <-- Same with horses

    displayGameState(meeting_number);
    endOfSeasonUpdate(horseData);
}
