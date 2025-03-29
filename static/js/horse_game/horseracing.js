import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed

async function getRaceData() {
    const raceData = await fetchTextFiles();
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

getRaceData();

console.log("Horsenames:", raceData.horsenames);