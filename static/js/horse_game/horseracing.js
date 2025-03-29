import { fetchTextFiles } from "./load_data.js"; // Adjust the path if needed

async function useRaceData() {
    const raceData = await fetchTextFiles();
    console.log("Race data in another file:", raceData);
    
    // Example usage
    console.log("Horsenames:", raceData.horsenames);
    shuffleArray(raceData.horsenames); // Shuffle the array
    console.log("Horsenames:", raceData.horsenames);
}

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1)); // Random index from 0 to i
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
}

useRaceData();

console.log("Horsenames:", raceData.horsenames);