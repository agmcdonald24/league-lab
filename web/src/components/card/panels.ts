// IP-4 (Wave I-P): the card's data panels in one chunk of their own (lazy.ts): the head paints with the page; the
// ratings and the charts follow (they wait for their own requests anyway). Keeps the app chunk's growth to the head.
export { default as Ratings } from "./Ratings.svelte";
export { default as PointsChart } from "./PointsChart.svelte";
export { default as RoleChart } from "./RoleChart.svelte";
