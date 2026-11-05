import { arena } from "../arena/production.js";

export const POST = (request) => arena().live(request);
