export async function fetchTextFiles() {
    const fileNames = ["horsenames.txt", "meetings.txt", "distances.txt", "racenames.txt", "money.txt"];
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

