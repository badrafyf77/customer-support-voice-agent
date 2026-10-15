/** Order scoped Darija output while retaining compatibility with unscoped English events. */
export class PlaybackGeneration {
  private highest = 0;
  private blockedThrough = 0;

  accept(id?: number) {
    if (id === undefined) return this.highest === 0;
    if (!Number.isSafeInteger(id) || id <= this.blockedThrough || id < this.highest) return false;
    this.highest = id;
    return true;
  }

  stop(id?: number) {
    if (id !== undefined && !Number.isSafeInteger(id)) return false;
    this.blockedThrough = Math.max(this.blockedThrough, id ?? this.highest);
    return id === undefined || id >= this.highest;
  }
}
