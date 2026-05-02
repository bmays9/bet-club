import {
    adjustRatingByAge
} from './initialise.js';

export let playerData = [];
export let horseData = [];
export let horsePool = [];
export let retiredHorses = [];
export let raceData = {};
export let meetingNumber = 0;
export let currentSeason = 1;
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

export function setHorsePool(data) {
    horsePool = data;
}

export function setRaceData(data) {
    raceData = data;
}

export function addRetiredHorses(horses) {
    retiredHorses = retiredHorses.concat(horses);
}

export function setCurrentSeason(num) {
    currentSeason = num;
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

export function getRetiredHorses() {
    return retiredHorses;
}

export function getCurrentSeason() {
    return currentSeason;
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

export function resetHorseRest(horses) {
    for (let horse of horses) {
        horse.rest = 1;
    }
}

export function incrementHorseAge(horses) {
    for (let horse of horses) {
        horse.age++;
        horse.rating = adjustRatingByAge(horse.baseRating, horse.age);
    }
}

export function fitnessModifier(fitnessLevel) {
    if (fitnessLevel === 1) return 0.8;
    if (fitnessLevel === 2) return 0.9;
    if (fitnessLevel === 3) return 1.0;
    if (fitnessLevel === 4) return 0.95;
    if (fitnessLevel === 5) return 0.9;
    if (fitnessLevel === 6) return 0.85;
    return 0.85;
}

export function getNearDistances(dist) {
    // Keys must match exact strings used in raceData.distances
    const distanceKeys = ["5f", "1m", "1m2f", "1m4f", "2m", "2m4f", "3m", "4m"];
    const index = distanceKeys.indexOf(dist);
    const near = [];
    if (index > 0) near.push(distanceKeys[index - 1]);
    if (index < distanceKeys.length - 1) near.push(distanceKeys[index + 1]);
    return near;
}

export function convertFractionalOddsToDecimal(fraction) {
    if (typeof fraction !== 'string') return Infinity;
    const [numerator, denominator] = fraction.split('/').map(Number);
    if (isNaN(numerator) || isNaN(denominator) || denominator === 0) return Infinity;
    return numerator / denominator;
}
