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