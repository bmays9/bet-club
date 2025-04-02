import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed

let meeting_number = 0;
let raceData = {}; // Declare raceData globally

async function getRaceData() {
    raceData = await fetchTextFiles();
    console.log("Race data in another file:", raceData);
    
    // Example usage
    console.log("Horsenames:", raceData.horsenames);
    shuffleArray(raceData.horsenames); // Shuffle the array
    raceData.horsenames = raceData.horsenames.slice(0, 144) // only need 6 * 24
    console.log("Horsenames:", raceData.horsenames);

}

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
}

function displayGameState(array) {

    console.log("Checking raceData:", raceData);

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
            <td>1.15</td>
            <td>${raceData.distances[meeting_number * 6 + i]}</td>
            <td>${raceData.racenames[meeting_number * 6 + i]}</td>
            <td>${raceData.prizemoney[meeting_number * 6 + i]}</td>
            </tr>`;
                }
    
    document.getElementById('gs-meeting-races').innerHTML = tableHtml;
}


async function runHorseRacing() {

    await getRaceData();
    displayGameState(meeting_number);

}



document.addEventListener("DOMContentLoaded", () => {
    runHorseRacing();
});