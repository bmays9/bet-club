import { raceEntries, playerData, horseData, raceData, setRaceEntries, setHorseData, setPlayerData, sortPlayerData, setRaceData, incrementHorseRest, fitnessModifier } from './gameState.js';
import { allEntries, canEnterRace, enterHorse, displayRaceEntries, allRacesHaveEntries } from './entry.js';
import { lineups , raceTime, meeting_number, incrementMeetingNumber, going, displayGameState, showHistoryModal } from './horseracing.js';
import { shuffleArray } from './initialise.js';

let gameRaceNumber = 0
let meetingRaceNumber = 0
let rDist = "";
let rGoing = "";
let rName = "";
let rGrade = "";
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

    // Randomize the Betting Order
    shuffleArray(playerData); // Shuffle the array
        
    console.log("Let's Race, gameracenume / racenum / meetingracenum", gameRaceNumber, racenum);
       document.getElementById('race-screen').style.display = "block";
    racecardBody.innerHTML = ""; // clear previous
    rDist = raceData.distances[gameRaceNumber];
    rGoing = raceData.goings[meeting_number];
    rName = raceData.racenames[gameRaceNumber];
    rTime = raceTime[racenum];
    rPrize = Number(raceData.prizemoney[gameRaceNumber]);
    rGrade = raceData.raceclass[gameRaceNumber]
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
    console.log("These ratings", ratedHorses);
    // priceHorses = assig---nOdds(ratedHorses); // Adds odds based on ability
    priceHorses = assignFormOdds(ratedHorses, rDist); // Adds odds based on form
    


    console.log("This Lineup", lineups[racenum]);
    console.log("These raceHorses", raceHorses);
    console.log("These prices", priceHorses);
    
    // Set Racecard Headers
    racecardHeader.innerHTML = `
        <tr>
            <th>No.</th>
            <th>Horse</th>
            <th>Trainer</th>
            <th>Form</th>
            <th>Odds</th>
            <th>Rating</th>
            <th>raceRating</th>
            <th>Bet</th>
        </tr>`

    entries.forEach((entry, index) => {
        const horse = horseData.find(h => h.name === entry.horseName);
        const pricedHorse = priceHorses[index]; // Get the horse with odds added
        console.log("Priced Horse", pricedHorse)
        const row = `
            <tr>
                <td>${index + 1}</td>
                <td>${entry.horseName}  <span class='text-body-secondary small-font'>(${horse.age})</td>
                <td>${entry.trainer}</td>
                <td>
                <a href="#" class="form-link" data-horse-name="${horse.name}">${horse.form}</a>
                </td>
                <td>${pricedHorse.odds}</td> <!-- odds now correctly displayed -->
                <td>${horse.rating}</td>
                <td>${pricedHorse.raceRating}</td>
                <td>${horse.bestDist}</td>
            </tr>
        `;
        racecardBody.innerHTML += row;
    });

    currentRatedHorses = ratedHorses;
    currentRacePrizes = rPrizes;

    // Event Listener for form and showing full history

    document.querySelectorAll('.form-link').forEach(link => {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            const horseName = this.getAttribute('data-horse-name');
            showHistoryModal(horseName);
        });
    });

    // nextRaceBtn.textContent = "Next Race";
    nextRaceBtn.disabled = true;
    startBtn.disabled = false;
}

function getHorseRatings(raceHorses, distanceStr, going) {
    const raceDistanceF = distanceToFurlongs(rDist);
  
    return raceHorses.map(horse => {

      let rating = horse.rating;
      console.log("THIS HORSE:", horse.name) 
      console.log("rating at the start", rating) 
      // Distance adjustment
      const bestDistF = horse.bestDist;
      const distDiff = Math.abs(bestDistF - raceDistanceF);
      const distPenalty = distDiff * horse.spread * 0.4;
      rating -= distPenalty;
      console.log("rating adjusted for distance: ", rating) 
  
      // Going preference adjustment
      const goingModifier = getGoingModifier(horse.goingPref, going);
      rating += goingModifier;
      console.log("rating adjusted for going: ", horse.goingPref, rating) 
  
      // Optional: other adjustments (age, rest, etc.)
      let fitness = fitnessModifier(horse.rest)
      
      rating = rating * fitness
      console.log("rating after fitness adjustment", rating)  
      rating += horse.wins * 3; //3 points every win.
    console.log("Race rating : ", Math.round(rating * 10) / 10)  
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

    // Step 1: Calculate implied probability and base odds using total of all ratings
    console.log("Ratesd horse info", ratedHorses)
    const totalRating = ratedHorses.reduce((sum, h) => sum + h.raceRating, 0);

    let horsesWithBaseOdds = ratedHorses.map(horse => {
        const relativeChance = horse.raceRating / totalRating;
        const impliedProbability = relativeChance;
        const decimalOdds = 1 / impliedProbability;
        console.log("Horse Base Odds - Start", horse.name, decimalOdds)
        return { ...horse, baseProbability: impliedProbability, decimalOdds };
    });
   


    // Step 2: Randomly adjust odds for 40 - 60% of horses
    const numToAdjust = Math.floor(Math.random() * (horsesWithBaseOdds.length * 0.2)) + Math.ceil(horsesWithBaseOdds.length * 0.4); // 0.2 is the range, 0.4 is the base
    const indicesToAdjust = new Set();

    while (indicesToAdjust.size < numToAdjust) {
        indicesToAdjust.add(Math.floor(Math.random() * horsesWithBaseOdds.length));
    }

    horsesWithBaseOdds = horsesWithBaseOdds.map((horse, i) => {
        if (indicesToAdjust.has(i)) {
            const adjustmentFactor = 1 + (Math.random() * 0.3 - 0.3); // +/-30%
            horse.decimalOdds *= adjustmentFactor;
            console.log("Adjustment Factor", adjustmentFactor)
            console.log("Horse Adjusted Odds", horse.name, horse.decimalOdds)
        }
        return horse;
    });


    // Step 3: Calculate new implied probabilities after adjustment
    horsesWithBaseOdds = horsesWithBaseOdds.map(horse => {
        horse.adjustedProbability = 1 / horse.decimalOdds;
        return horse;
    });

    // Step 4: Calculate total overround
    let totalProbability = horsesWithBaseOdds.reduce((sum, h) => sum + h.adjustedProbability, 0);
    console.log("totalProbability", totalProbability)

    // Step 5: Adjust one horse to bring overround to 100–110%
    horsesWithBaseOdds = adjustOverround(horsesWithBaseOdds, 1.0, 1.15);

    console.log("Horse Base Odds - after overround adjustment",horsesWithBaseOdds)
    totalProbability = horsesWithBaseOdds.reduce((sum, h) => sum + h.adjustedProbability, 0);
    console.log("totalProbability at the end", totalProbability)

    // Step 6: Final formatting
    return horsesWithBaseOdds.map(horse => {
        return {
            ...horse,
            odds: formatOdds(horse.decimalOdds)
        };
    });
}
    // order the odds by their relative chance - favourite has the lowest odds. The odds dont have to reflect the relative chance exactly, as the player doesnt know the ratings.
    // select between 1/3 and 1/4 of the horses to randomly adjust the odds. Up or down, by a random amount 
    // then select another horse to adjust to make the overround of odds between 100% and 110% 
    // later I will want to adjust the odds for horse.wins and horse.form



// Utility: Convert distance string to furlongs
function distanceToFurlongs(distStr) {
    console.log("distStr", distStr);
    
    // Just furlongs, like "5f"
    if (/^\d+f$/.test(distStr)) {
        return parseInt(distStr);
    }

    // Miles and furlongs, like "1m4f" or "3m"
    const match = distStr.match(/^(\d+)m(?:([0-9]+)f)?$/);

    if (!match) {
        console.warn("Could not parse distance:", distStr);
        return 0;
    }

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


function adjustOverround(horses, minOverround = 1.0, maxOverround = 1.15) {
    const targetOverround = minOverround + Math.random() * (maxOverround - minOverround);
    let currentOverround = horses.reduce((sum, h) => sum + (1 / h.decimalOdds), 0);

    // Pick one random horse to adjust
    const adjustIndex = Math.floor(Math.random() * horses.length);
    let adjustmentAttempts = 0;
    const maxAttempts = 100;

    while ((currentOverround < minOverround || currentOverround > maxOverround) && adjustmentAttempts < maxAttempts) {
        const horse = horses[adjustIndex];
        const currentProbability = 1 / horse.decimalOdds;

        // Calculate needed scale factor for this horse only
        const adjustmentFactor = targetOverround / currentOverround;
        const newProbability = currentProbability * adjustmentFactor;

        // Clamp adjustment between 0.01 and 0.99 to avoid weird odds
        const clampedProbability = Math.min(Math.max(newProbability, 0.01), 0.99);

        horse.decimalOdds = 1 / clampedProbability;
        horse.adjustedProbability = clampedProbability;

        // Recalculate total overround
        currentOverround = horses.reduce((sum, h) => sum + (1 / h.decimalOdds), 0);
        adjustmentAttempts++;
    }

    return horses;
}

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
    const maxVariance = Math.max(...horses.map(h => h.raceRating)) / 10;
    console.log("Variance as part of Max rating" ,maxVariance)
    const horsesWithRoll = horses.map(horse => {
        const posneg = Math.random() < 0.5 ? -1 : 1;
        const variance = (Math.random()) * maxVariance * posneg; // Tweakable randomness factor +or -  10% of the max rating
        const finalScore = horse.raceRating + variance;  // pure ability + noise
        console.log("Horse Rating, and after variance" ,horse.raceRating, finalScore)
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
    rGrade = raceData.raceclass[gameRaceNumber]
    console.log("Before we update, here's the finishingOrder being sent", finishingOrder)
    updateHorseData(finishingOrder, rGrade)
    updatePlayerData(finishingOrder)
    
}

function updateHorseData(results, grade) {
    results.forEach((horse, index) => {
        const horseIndex = horseData.findIndex(h => h.name === horse.name);
        if (horseIndex !== -1) {
            const pos = (index + 1) <= 9 ? index + 1 : 0;
            const h = horseData[horseIndex];
            let rGoing = raceData.goings[meeting_number];

            // Add short form (e.g. "1", "2", etc.)
            h.form = (h.form || "") + pos;

            // Add long form (e.g. "1m2-Good-3")
            const formLongEntry = `${rDist}-${rGoing}-${pos}`;
            h.formLong = (h.formLong || "") + (h.formLong ? "," : "") + formLongEntry;

            // Add win
            if (pos === 1) {
                h.wins = (h.wins || 0) + 1;
            }

            // Add Grade 1 win
            
            if (!h.grade1s) h.grade1s = {};
            if (pos === 1 && grade === 1) {
                if (!h.grade1s[rDist]) {
                    h.grade1s[rDist] = 1;
                } else {
                    h.grade1s[rDist] += 1;
                }
            }

            // Reset rest
            h.rest = -1;

            // Add run number
            h.runs = (h.runs || 0) + 1;

            // Add prize money
            const prizeMoney = Number(rPrizes[index]) || 0;
            h.money = (h.money || 0) + prizeMoney;

            // ✅ Add full race history entry
            let rCourse = raceData.meetings[meeting_number];
            console.log("rgoing:" , rGoing);
            
            h.history = h.history || [];
            h.history.push({
                meeting: meeting_number + 1,
                course: rCourse,
                name: rName,
                going: rGoing,
                distance: rDist,
                position: pos,
                winnings: prizeMoney
            });

            // Update the horseData array
            horseData[horseIndex] = h;
        }
    });

    // Enable next race button
    startBtn.disabled = true;
    nextRaceBtn.disabled = false;
}


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
    console.log("HandleNextRace!!!!!!!!!XXXXXXXX");
    console.log("HandleNextRace - MeetingRace:", meetingRaceNumber);

    // 🔁 Move increment to the top
    meetingRaceNumber++;
    gameRaceNumber++;

    console.log("meetingRaceNumber +1. Now it's: ", meetingRaceNumber);
    console.log("gameRaceNumber +1. Now it's: ", gameRaceNumber);

    if (meetingRaceNumber == 6) {
        console.log("End of meeting reached.");
        nextRaceBtn.textContent = "Next Race"; // reset for next meeting
        startBtn.disabled = true;
        nextRaceBtn.disabled = false;
        handleContinueToNextMeeting();
        return;
    }

    // Before the 6th race, show "Continue" next time
    if (meetingRaceNumber === 5) {
        console.log("meetingRaceNumber IS 5 ", meetingRaceNumber);
        document.getElementById('next-race').textContent = "Continue";
    } else {
        console.log("meetingRaceNumber IS NOT 5 ", meetingRaceNumber);
        nextRaceBtn.textContent = "Next Race";
    }

    showRacecard(meetingRaceNumber);

    startBtn.disabled = false;
    nextRaceBtn.disabled = true;
}

function handleContinueToNextMeeting() {
    console.log("Continuing to next meeting...");
    // update horse rest +1
    incrementHorseRest(horseData)


    
    if (meeting_number < 16) {
        incrementMeetingNumber();  // Advance the meeting
        meetingRaceNumber = 0;
        
        nextRaceBtn.textContent = "Next Race";
        nextRaceBtn.disabled = true;
        startBtn.disabled = true;

        displayGameState(meeting_number);  // Your function to set up the next meeting
    } else {
        displayFinalStandings();
        nextRaceBtn.disabled = true;
    }
}

function assignFormOdds(raceHorses, targetDistanceStr) {
    console.log(`--- Assigning Form-Based Odds for Distance ${targetDistanceStr} ---`);

    const targetDist = distanceToFurlongs(targetDistanceStr);

    const formScores = raceHorses.map(horse => {
        let score = 0;
        if (horse.history && horse.history.length) {
            for (let race of horse.history) {
                const histDist = distanceToFurlongs(race.distance);
                const distDiff = Math.abs(histDist - targetDist);

                // Score weight decreases with distance mismatch
                const distanceWeight = Math.max(0, 1 - distDiff / 10); // Tweak divisor as needed

                if (!isNaN(race.position) && race.position > 0) {
                    const positionScore = Math.max(0, (10 - race.position)); // 1st = 9, 2nd = 8, ...
                    score += positionScore * distanceWeight;
                }
            }
        }
        return { horse, score };
    });

    console.log("Form Scores:");
    formScores.forEach(entry => {
        console.log(`${entry.horse.name}: ${entry.score.toFixed(2)}`);
    });

    // Normalize scores to probabilities
    const totalScore = formScores.reduce((sum, h) => sum + h.score, 0) || 1;
    const probEntries = formScores.map(entry => ({
        horse: entry.horse,
        impliedProb: entry.score / totalScore
    }));

    // Apply random overround (between 1.02 and 1.15)
    const overround = 1 + (Math.random() * 0.13 + 0.02);
    console.log("Using overround multiplier:", overround.toFixed(4));

    const adjustedProbs = probEntries.map(entry => ({
        horse: entry.horse,
        adjustedProb: Math.min(entry.impliedProb * overround, 1) // cap at 100%
    }));

    // Match to nearest fractional odds
    const assignedOdds = adjustedProbs.map(entry => {
        const bestMatch = commonOddsWithProb.reduce((closest, current) => {
            const diff = Math.abs(current.impliedProb - entry.adjustedProb);
            return diff < closest.diff ? { ...current, diff } : closest;
        }, { diff: Infinity });

        return {
            horseName: entry.horse.name,
            odds: `${bestMatch.num}/${bestMatch.denom}`,
            impliedProb: entry.adjustedProb
        };
    });

    console.log("Final Assigned Odds:");
    assignedOdds.forEach(o => {
        console.log(`${o.horseName}: ${o.odds} (prob: ${o.impliedProb.toFixed(3)})`);
    });

    return assignedOdds;
}

