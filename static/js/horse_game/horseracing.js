import { fetchTextFiles } from "./load_data.js";
import { allEntries, canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries } from './entry.js';
import { shuffleArray, getRandomGoingPreference, buildHorseData, adjustRatingByAge, endOfSeasonUpdate, goingModifier, resetPlayerData } from './initialise.js';
import { raceEntries, playerData, horseData, raceData, setRaceEntries, setHorseData, setPlayerData, setRaceData } from './gameState.js';

let meeting_number = 0;
let raceTime = ["1:15", "1:50", "2:25", "3:00", "3:35", "4:10"]
let players = []
const TOTALHORSES = 144
let going = ["Soft-Ish", "Sofyt"];
let selectedRaceIndex = null;
let lineups = []; // stores final race line ups, taken from raceEntries after they are confirme


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
    setRaceEntries({
        0: [],
        1: [],
        2: [],
        3: [],
        4: [],
        5: []
      });


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
                entries[0]?.horseName || "",
                entries[1]?.horseName || "",
                entries[2]?.horseName || ""
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
    let playerName = playerData[currentPlayerIndex].name;

    // Insert button and stable HTML
    document.getElementById('page-info').innerHTML = `${playerName}'s stable and race selections. <br>
    <button id="confirm-selections" class="btn btn-sm btn-primary">Finish</button>
    <button id="auto-selections" class="btn btn-sm btn-primary">Test</button>`;
    let confirmBtn = document.getElementById("confirm-selections");
    confirmBtn.disabled = true; // Initially disable
    let testBtn = document.getElementById("auto-selections");

    let playerHorses = horseData.filter(horse => horse.owner === playerName);

    let stableHtml = `
        <tr>
            <th>Sel</th>
            <th>Fit</th>
            <th>Name</th>
            <th>R</th>
            <th>W</th>
            <th>Winnings</th>
            <th>Form</th>
        </tr>
    `;

    // Loop over player's horses and display stable data
    for (let i = 0; i < playerHorses.length; i++) {
        const horse = playerHorses[i];

        let enteredRaceIndex = null;
        for (let j = 0; j < 6; j++) {
            if (raceEntries[j].includes(horse.name)) {
                enteredRaceIndex = j;
                break;
            }
        }

        const entrySymbol = enteredRaceIndex !== null ? `${enteredRaceIndex + 1}` : "➤";
        const rowClass = enteredRaceIndex !== null ? "table-success" : "";

        stableHtml += `
            <tr class="${rowClass}">
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

    // Event listener for horse selection
    document.querySelectorAll('.horse-entry-btn').forEach(button => {
        button.addEventListener('click', function () {
            if (selectedRaceIndex === null) {
                alert("Please select a race first.");
                return;
            }

            const horseName = this.getAttribute('data-horse-name');
            playerName = playerData[currentPlayerIndex].name;
            console.log("Horsename:", horseName)
            console.log("Playername:", playerName)

            const entered = enterHorse(playerName, horseName, selectedRaceIndex);
            console.log("Entered: ", entered);
            if (entered) {

                displayRaceSelections(); // Update selections
                displayStable(currentPlayerIndex); // Re-render stable

                // Check if all races have been entered and enable the button
                let check = allRacesHaveEntries();
                console.log("ARHE", check);
                if (allRacesHaveEntries()) {
                    confirmBtn.disabled = false;
                } else {
                    confirmBtn.disabled = true;
                }
            }
        });
    });

    // event listener for testing
    testBtn.onclick = function () {
        playerName = playerData[currentPlayerIndex].name;
        playerHorses = horseData.filter(horse => horse.owner === playerName);
    
        // Clear existing entries without reassigning
        for (let i = 0; i < 6; i++) {
            raceEntries[i] = [];
        }
    
        // Add the first 6 horses to each of the 6 races (1 per race)
        for (let i = 0; i < 6; i++) {
            const horse = playerHorses[i];
            if (horse) {
                raceEntries[i].push({ playerName, horseName: horse.name });
            }
        }
    
        displayRaceSelections();
        displayStable(currentPlayerIndex);
    
        if (confirmBtn) {
            confirmBtn.disabled = false; // enable the finish button
        }
    };

    // Confirm button to save entries and move to the next player
    confirmBtn.onclick = function () {
        lineups.push({
            player: playerData[currentPlayerIndex].name,
            entries: JSON.parse(JSON.stringify(raceEntries)) // Deep copy
        });

        // Clear existing entries without reassigning
        for (let i = 0; i < 6; i++) {
            raceEntries[i] = [];
        }

        currentPlayerIndex++;

        if (currentPlayerIndex >= playerData.length) {
            alert("All players have selected their entries!");
            return;
        }

        displayRaceSelections();
        displayStable(currentPlayerIndex); // Display next player's stable
        this.disabled = true; // Disable the confirm button again after action
    };

    // Ensure the button is updated correctly if all races have entries
    if (allRacesHaveEntries()) {
        confirmBtn.disabled = false;
    } else {
        confirmBtn.disabled = true;
    }
}


export async function runHorseRacing(players) {
    await buildRaceData();
    const builtData = resetPlayerData(players); // <-- BUILD playerData
    setPlayerData(builtData);                   // <-- SAVE to shared state

    setHorseData(buildHorseData());             // <-- Same with horses

    displayGameState(meeting_number);
    endOfSeasonUpdate(horseData);
}
