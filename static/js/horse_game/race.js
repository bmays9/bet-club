import { raceEntries, playerData, horseData, raceData, setRaceEntries, setHorseData, setPlayerData, sortPlayerData, setRaceData } from './gameState.js';
import { allEntries, canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries } from './entry.js';
import { lineups , raceTime, meeting_number, incrementMeetingNumber, going, displayGameState } from './horseracing.js';

let gameRaceNumber = 0
let meetingRaceNumber = 0
let rDist = "";
let rGoing = "";
let rName = "";
let rTime = "";
let rPrize = "";
let entries = [];
let priceHorses = [];
let rPrizes = [];
const racecardBody = document.getElementById("racecard-body");
const racecardHeader = document.getElementById("racecard-header");
let startBtn = document.getElementById('start-race');
let nextRaceBtn = document.getElementById('next-race');
let currentRatedHorses = [];
let currentRacePrizes = [];

startBtn.addEventListener('click', () => {
    const result = simulateRace(currentRatedHorses);
    displayResults(result);
});

export function showRacecard (racenum) {

    console.log("Here's the horse Data" , horseData)
    console.log("Player Data before we start", playerData)
        
    console.log("Let's Race, gameracenume / racenum", gameRaceNumber, racenum);
    document.getElementById('race-screen').style.display = "block";
    racecardBody.innerHTML = ""; // clear previous
    rDist = raceData.distances[gameRaceNumber];
    rGoing = going[meeting_number];
    rName = raceData.racenames[gameRaceNumber];
    rTime = raceTime[racenum];
    rPrize = Number(raceData.prizemoney[gameRaceNumber]);
    entries = lineups[racenum];

    // Calculate 1,2,3 Prize Money
    let rPrize1 = Math.round(Number(rPrize) * 0.65);
    console.log("rPrize1: ", rPrize1)
    let rPrize2 = Math.round(Number(rPrize) * 0.25);
    console.log("rPrize2: ", rPrize2)
    let rPrize3 = Math.round(Number(rPrize) * 0.10);
    rPrizes = [rPrize1, rPrize2, rPrize3];
    // Display Race Details
    const dTime = document.getElementById("r-time"); 
    dTime.innerHTML = `${rTime} | `;
    const dName = document.getElementById("r-name");
    dName.innerHTML = rName;
    const dDist = document.getElementById("r-dist");
    dDist.innerHTML = rDist;
    const dPrize = document.getElementById("r-prize")
    dPrize.innerHTML = rPrize;
    const dRunners = document.getElementById("r-runners");
    dRunners.innerHTML = `${entries.length}`;

    // feed race conditions into the ratings system to get the horses ability, distance, going
    
    let raceHorses = entries.map(entry =>
        horseData.find(h => h.name === entry.horseName)
    );

    const ratedHorses  = getHorseRatings(raceHorses, rDist, rGoing);

    priceHorses = assignOdds(ratedHorses); // Adds odds based on ability
    


    console.log("This Lineup", lineups[racenum]);
    console.log("These raceHorses", raceHorses);
    console.log("These ratings", ratedHorses);
    console.log("These prices", priceHorses);
    
    // Set Racecard Headers
    racecardHeader.innerHTML = `
        <tr>
            <th>No.</th>
            <th>Horse</th>
            <th>Trainer</th>
            <th>Form</th>
            <th>Odds</th>
        </tr>`

    entries.forEach((entry, index) => {
        const horse = horseData.find(h => h.name === entry.horseName);
        const pricedHorse = priceHorses[index]; // Get the horse with odds added
        const row = `
            <tr>
                <td>${index + 1}</td>
                <td>${entry.horseName}</td>
                <td>${entry.trainer}</td>
                <td>${horse.form}</td>
                <td>${pricedHorse.odds}</td> <!-- odds now correctly displayed -->
            </tr>
        `;
        racecardBody.innerHTML += row;
    });

    currentRatedHorses = ratedHorses;
    currentRacePrizes = rPrizes;

    
}

function getHorseRatings(raceHorses, distanceStr, going) {
    const raceDistanceF = distanceToFurlongs(rDist);
  
    return raceHorses.map(horse => {
      let rating = horse.rating;
  
      // Distance adjustment
      const bestDistF = horse.bestDist;
      const distDiff = Math.abs(bestDistF - raceDistanceF);
      const distPenalty = distDiff * horse.spread * 0.2;
      rating -= distPenalty;
  
      // Going preference adjustment
      const goingModifier = getGoingModifier(horse.goingPref, going);
      rating += goingModifier;
  
      // Optional: other adjustments (age, rest, etc.)
      rating -= horse.rest * 0.2;
      rating += horse.wins * 0.5;
  
      return {
        ...horse,
        raceRating: Math.round(rating * 10) / 10 // rounded rating for this race
      };
    });
  }
  
// Utility: Compare going preference
function getGoingModifier(pref, actual) {
    const options = ["Heavy", "Soft", "Good-Soft", "Good", "Good-Firm"];
    const diff = Math.abs(options.indexOf(pref) - options.indexOf(actual));
    return -diff * 1.5; // penalty for mismatch
}

function assignOdds(ratedHorses) {
    const maxRating = Math.max(...ratedHorses.map(h => h.rating));
    return ratedHorses.map(horse => {
        const relativeChance = horse.rating / maxRating;
        const impliedOdds = 1 / relativeChance;
        const formattedOdds = formatOdds(impliedOdds);
        return { ...horse, odds: formattedOdds };
    });
}

// Utility: Convert distance string to furlongs
function distanceToFurlongs(distStr) {
    console.log("distStr", distStr)
    if (distStr.endsWith("f")) return parseInt(distStr); // e.g., 5f = 5
    const match = distStr.match(/(\d+)m(\d+)?/); // e.g., 1m4 = 12 + 4 = 16f
    if (!match) return 0;
    const miles = parseInt(match[1]);
    const furlongs = match[2] ? parseInt(match[2]) : 0;
    return miles * 8 + furlongs;
  }

  const commonFractionalOdds = [
    [1, 10], [1, 8], [1, 6], [2, 11], [1, 5], [4, 9], [1, 4], [2, 7], [3, 10],
    [1, 3], [4, 11], [2, 5], [4, 9], [8, 15], [4, 7], [8, 13], [4, 6], [4, 5],
    [5, 6], [10, 11], [1, 1], [11, 10], [5, 4], [6, 5], [11, 8], [7, 5], [6, 4],
    [3, 2], [13, 8], [7, 4], [15, 8], [2, 1], [9, 4], [5, 2], [11, 4], [3, 1],
    [10, 3], [7, 2], [4, 1], [9, 2], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1], [10, 1],
];

const commonOddsWithProb = commonFractionalOdds.map(([num, denom]) => {
    const impliedProb = denom / (num + denom);
    return { num, denom, impliedProb };
});

function formatOdds(impliedOdds) {
    const impliedProb = 1 / impliedOdds;
    let closest = commonOddsWithProb[0];
    let minDiff = Math.abs(impliedProb - closest.impliedProb);

    for (const odds of commonOddsWithProb) {
        const diff = Math.abs(impliedProb - odds.impliedProb);
        if (diff < minDiff) {
            closest = odds;
            minDiff = diff;
        }
    }

    return `${closest.num}/${closest.denom}`;
}

function simulateRace(horses) {
    const horsesWithRoll = horses.map(horse => {
        const variance = (Math.random() - 0.5) * 0.3; // Tweakable randomness factor
        const finalScore = horse.rating + variance;  // pure ability + noise
        return { ...horse, finalScore };
    });

    horsesWithRoll.sort((a, b) => b.finalScore - a.finalScore);

    return horsesWithRoll;
}

function displayResults(finishingOrder) {
    
    racecardBody.innerHTML = "";

    finishingOrder.forEach((horse, index) => {
        const odds = priceHorses.find(h => h.name === horse.name)?.odds || "?";

    // Set Racecard Headers
    racecardHeader.innerHTML = `
        <tr>
            <th>Pos.</th>
            <th>Horse</th>
            <th>Trainer</th>
            <th>Odds</th>
            <th>Winnings</th>
        </tr>`

        const row = `
            <tr>
                <td>${index + 1}</td>
                <td>${horse.name}</td>
                <td>${horse.owner || "?"}</td>
                <td>${odds}</td>
                <td>${index < 3 ? rPrizes[index] : ""}</td>
            </tr>
        `;
        racecardBody.innerHTML += row;
    });

    // update horseData
    console.log("Before we update, here's the finishingOrder being sent", finishingOrder)
    updateHorseData(finishingOrder)
    updatePlayerData(finishingOrder)

}

function updateHorseData(results) {
    results.forEach((horse, index) => {
        const horseIndex = horseData.findIndex(h => h.name === horse.name);
        if (horseIndex !== -1) {
            const pos = index + 1;
            const h = horseData[horseIndex];

            // Add short form (e.g. "1", "2", etc.)
            h.form = (h.form || "") + pos;

            // Add long form (e.g. "1m2-Good-3")
            const formLongEntry = `${rDist}-${rGoing}-${pos}`;
            h.formLong = (h.formLong || "") + (h.formLong ? "," : "") + formLongEntry;

            // Add win
            if (pos === 1) {
                h.wins = (h.wins || 0) + 1;
            }

            // Reset Rest 
            h.rest = -1; // will be zero when all horses are + 1 at the end of the meeting            

            // Add run number
            h.runs = h.runs + 1;

            // Add prize money
            const prizeMoney = rPrizes[index];
            if (prizeMoney) {
                h.money = (h.money || 0) + Number(prizeMoney);
            }

            // Update the horseData array
            horseData[horseIndex] = h;
        }
    });

    // display next race button.
    startBtn.disabled = true
    nextRaceBtn.disabled = false

};


document.getElementById('next-race').addEventListener('click', handleNextRace);

function updatePlayerData(results) {
    results.forEach((horse, index) => {
        console.log("Updating Playe using horse", horse)
        const ownerName = horse.owner;
        const pos = index + 1;
        const playerIndex = playerData.findIndex(p => p.name === ownerName);
        console.log("updating playerData: ", playerData)
        console.log("updating playerData Index: ", playerIndex)
        if (playerIndex !== -1) {
            const player = playerData[playerIndex];

            // Add win for 1st place
            console.log("Pos", pos)
            if (pos === 1) {
                player.wins = (player.wins || 0) + 1;
            }

            // Add prize money for top 3
            const prizeMoney = rPrizes[index];
            if (prizeMoney) {
                console.log("Player Winnings", prizeMoney)
                player.winnings = (player.winnings || 0) + Number(prizeMoney);
                player.total = (player.total || 0) + Number(prizeMoney);
            }

            // Handle Entry Fee
            rPrize = Number(raceData.prizemoney[gameRaceNumber]);
            const entryFee = Number(rPrize) * 0.1 ;
            
            console.log("Player Entry", entryFee  )
            player.entries = (player.entries || 0) + Number(entryFee);
            player.total = (player.total || 0) - Number(entryFee);
            
            // Update the playerData array
            playerData[playerIndex] = player;

            console.log("All playerData Now after player updated: ", playerData)
        }
    });
}


function handleNextRace() {
    meetingRaceNumber++;
    console.log("HandleNextRae - MeetingraceNumber", meetingRaceNumber)

    if (meetingRaceNumber >= 6) {
        // End of meeting
        if (meeting_number < 15) { // Only move to next meeting if fewer than 16 total
            console.log("MeetingraceNumber >= 6, display game state", meetingRaceNumber)
            incrementMeetingNumber(); // ✅ works
            meetingRaceNumber = 0;
            handleContinueToNextMeeting(); 
            
            

            // Replace the handler for the continue phase
            nextRaceBtn.removeEventListener('click', handleNextRace);
            nextRaceBtn.addEventListener('click', handleContinueToNextMeeting);

        } else {
          
            // All 16 meetings complete
            displayFinalStandings(); // You need to define this function
            nextRaceBtn.disabled = true;

            
        }

    } else {
        // Continue to next race in the current meeting
        gameRaceNumber++;
        showRacecard(meetingRaceNumber);
        if (meetingRaceNumber == 5) {
            nextRaceBtn.textContent = "Continue";
        }
        startBtn.disabled = false;
        nextRaceBtn.disabled = true;
    }
}

function handleContinueToNextMeeting() {
    // Let players enter new horses

    nextRaceBtn.textContent = "Next Race";
    nextRaceBtn.disabled = true;
    startBtn.disabled = true;

    // Reset horses' rest days, clear selections, or any other prep work here
    horseData.forEach(horse => {
        if (typeof horse.rest === 'number') {
            horse.rest += 1;
        } else {
            horse.rest = 1; // if undefined, initialize it
        }
    });

    //prepareForNextMeeting(); // You should define this function to handle resetting
    console.log("All playerData before sorting: ", playerData)
    sortPlayerData();
    console.log("All playerData Now after sorting: ", playerData)

    // Reassign original handler
    // nextRaceBtn.removeEventListener('click', handleContinueToNextMeeting);
    // nextRaceBtn.addEventListener('click', handleNextRace);

    displayGameState(); // Show standings or summary
}
