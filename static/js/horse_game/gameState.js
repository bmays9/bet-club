export let playerData = [];
export let horseData = [];
export let raceData = {};
export let meetingNumber = 0;
export let raceEntries = {
    0: [],
    1: [],
    2: [],
    3: [],
    4: [],
    5: []
  };

export function setPlayerData(data) {
    playerData = data;
}

export function sortPlayerData() {
    playerData.sort((a, b) => (b.total || 0) - (a.total || 0));
}


export function setHorseData(data) {
    horseData = data;
}

export function setRaceData(data) {
    raceData = data;
}

export function setRaceEntries(data) {
    raceEntries = data;
}

export function setMeetingNumber(num) {
    meetingNumber = num;
}

// Getters
export function getPlayerData() {
    return playerData;
}

export function getHorseData() {
    return horseData;
}

export function getRaceData() {
    return raceData;
}

export function getRaceEntries() {
    return raceEntries;
}

export function getMeetingNumber() {
    return meetingNumber;
}

// checkers 
export function allRacesHaveEntries() {
    for (let i = 0; i < 6; i++) {
        if ((raceEntries[i] || []).length === 0) {
            return false;
        }
    }
    return true;
}

export function incrementHorseRest(horses) {
    for (let horse of horses) {
        horse.rest++;
    }
}

export function fitnessModifier(fitnessLevel) {
    if (fitnessLevel === 0) return 0.8;
    if (fitnessLevel === 1) return 0.85;
    if (fitnessLevel === 2) return 0.9;
    if (fitnessLevel === 3) return 1.0;
    if (fitnessLevel === 4) return 0.95;
    if (fitnessLevel === 5) return 0.9;
    
    return 0.85;
}