// load_data.js
import { runHorseRacing } from "./horseracing.js";

// Exported player array if needed elsewhere
export let players = [];

// Load race data from text files
export async function fetchTextFiles() {
    const fileNames = [
        "horsenames.txt",
        "meetings.txt",
        "distances.txt",
        "racenames.txt",
        "prizemoney.txt"
    ];
    const baseUrl = "/static/data/horse_game/";
    const fileData = {};

    for (const file of fileNames) {
        try {
            const response = await fetch(`${baseUrl + file}?v=${Date.now()}`);
            if (!response.ok) throw new Error(`Failed to load ${file}`);
            const text = await response.text();
            fileData[file.replace('.txt', '')] = text.split("\n").map(line => line.trim());
        } catch (error) {
            console.error(`Error loading ${file}:`, error);
        }
    }

    console.log("Loaded file data:", fileData);
    return fileData;
}

// When page is ready, show modal and collect players
document.addEventListener("DOMContentLoaded", function () {
    const myModal = new bootstrap.Modal(document.getElementById("gameOptionsModal"));
    myModal.show();

    // Attach label toggles to each checkbox
    for (let i = 1; i <= 6; i++) {
        const checkbox = document.getElementById(`p${i}-check`);
        const label = document.getElementById(`p${i}-label`);
        checkbox.addEventListener("change", () => {
            label.textContent = checkbox.checked ? "Human Player" : "AI Player";
        });
    }

    // Start game on button click
    document.getElementById("start-game").addEventListener("click", function () {
        const nameInputs = document.querySelectorAll('.player-name');
        const playersList = [];

        for (let i = 1; i <= 6; i++) {
            const input = document.getElementById(`p${i}-name`);
            const checkbox = document.getElementById(`p${i}-check`);
            const name = input?.value.trim().slice(0, 12) || `Player ${i}`;
            const isHuman = checkbox?.checked || false;

            players.push({ name, human: isHuman });
        }

        console.log("Collected players:", players);
        document.activeElement.blur(); // Remove focus from button
        myModal.hide();

        // Start game
        console.log(players)
        runHorseRacing(players);
    });
});