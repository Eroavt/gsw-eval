import { arena } from "../arena/production.js";

export const GET = (request) => arena().exportVotes(request);
