export class ApiError extends Error {
  constructor(
    message: string,
    readonly code = "NETWORK_ERROR",
    readonly requestId?: string,
    readonly httpStatus?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
