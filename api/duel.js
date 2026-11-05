import { arena } from "../arena/production.js";

export const GET = (request) => arena().duel(request);
