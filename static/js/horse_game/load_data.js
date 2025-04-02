export async function fetchTextFiles() {
    const fileNames = ["horsenames.txt", "meetings.txt", "distances.txt", "racenames.txt", "prizemoney.txt"];
    const baseUrl = "/static/data/horse_game/";  // Ensure Django serves static files
    const fileData = {};

    for (const file of fileNames) {
        try {
            const response = await fetch(baseUrl + file);
            if (!response.ok) throw new Error(`Failed to load ${file}`);
            const text = await response.text();
            fileData[file.replace('.txt', '')] = text.split("\n").map(line => line.trim());
        } catch (error) {
            console.error(`Error loading ${file}:`, error);
        }
    }
    console.log(fileData); // Object with arrays for each file
    return fileData; // If you need to use it elsewhere
}

document.addEventListener("DOMContentLoaded", function () {
    let myModal = new bootstrap.Modal(document.getElementById('gameOptionsModal'));
    myModal.show();

    // Function to toggle label text
    function togglePlayerLabel(checkboxId, labelId) {
        let checkbox = document.getElementById(checkboxId);
        let label = document.getElementById(labelId);

        checkbox.addEventListener("change", function () {
            label.textContent = checkbox.checked ? "Human Player" : "AI Player";
        });
    }
        
    // Apply function to all player checkboxes
    for (let i = 1; i <= 6; i++) {
        togglePlayerLabel(`p${i}-check`, `p${i}-label`);
    }

    document.getElementById("start-game").addEventListener("click", function () {
        let players = [];

        for (let i = 1; i <= 6; i++) {
            let playerNameInput = document.getElementById(`p${i}-name`);
            let playerCheckbox = document.getElementById(`p${i}-checkbox`);

            let playerName = playerNameInput ? playerNameInput.value.trim() : `Player ${i}`;
            let isHuman = playerCheckbox ? playerCheckbox.checked : false;

            // Validate name length
            if (playerName.length > 12) {
                alert(`Player ${i} name must be 12 characters or fewer!`);
                return;
            }

            // Store player data
            players.push({
                name: playerName || `Player ${i}`, // Default if empty
                human: isHuman
            });
        }

        console.log(players); // Log player data
        myModal.hide(); // Hide the modal after validation
        // You can now use `players` array in your game logic
    });
});