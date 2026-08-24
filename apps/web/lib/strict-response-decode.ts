export type DecodeFailure = (path: string, reason: string) => never;

export class StrictResponseDecoder {
  private readonly fail: DecodeFailure;

  constructor(fail: DecodeFailure) {
    this.fail = fail;
  }

  record(raw: unknown, path: string): Record<string, unknown> {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return this.fail(path, "expected_object");
    }
    return raw as Record<string, unknown>;
  }

  field(value: Record<string, unknown>, key: string, path: string): unknown {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      return this.fail(`${path}.${key}`, "missing_required_field");
    }
    return value[key];
  }

  string(raw: unknown, path: string, allowEmpty = false): string {
    if (typeof raw !== "string" || (!allowEmpty && raw.length === 0)) {
      return this.fail(
        path,
        allowEmpty ? "expected_string" : "expected_non_empty_string",
      );
    }
    return raw;
  }

  boolean(raw: unknown, path: string): boolean {
    if (typeof raw !== "boolean") {
      return this.fail(path, "expected_boolean");
    }
    return raw;
  }

  integer(
    raw: unknown,
    path: string,
    minimum = 0,
    maximum = Number.MAX_SAFE_INTEGER,
  ): number {
    if (
      !Number.isSafeInteger(raw) ||
      (raw as number) < minimum ||
      (raw as number) > maximum
    ) {
      return this.fail(path, `expected_safe_integer_${minimum}_to_${maximum}`);
    }
    return raw as number;
  }

  finiteNumber(
    raw: unknown,
    path: string,
    minimum = -Number.MAX_VALUE,
    maximum = Number.MAX_VALUE,
  ): number {
    if (
      typeof raw !== "number" ||
      !Number.isFinite(raw) ||
      raw < minimum ||
      raw > maximum
    ) {
      return this.fail(path, `expected_finite_number_${minimum}_to_${maximum}`);
    }
    return raw;
  }

  enumeration<T extends string>(raw: unknown, values: readonly T[], path: string): T {
    if (typeof raw !== "string" || !values.includes(raw as T)) {
      return this.fail(path, `unexpected_enum_${String(raw)}`);
    }
    return raw as T;
  }

  array<T>(
    raw: unknown,
    path: string,
    decode: (item: unknown, itemPath: string, index: number) => T,
  ): T[] {
    if (!Array.isArray(raw)) {
      return this.fail(path, "expected_array");
    }
    return raw.map((item, index) => decode(item, `${path}[${index}]`, index));
  }

  stringArray(raw: unknown, path: string, allowEmptyItems = false): string[] {
    return this.array(raw, path, (item, itemPath) =>
      this.string(item, itemPath, allowEmptyItems)
    );
  }

  nullable<T>(
    raw: unknown,
    path: string,
    decode: (item: unknown, itemPath: string) => T,
  ): T | null {
    return raw === null ? null : decode(raw, path);
  }

  unique<T extends string | number>(values: T[], path: string): void {
    if (new Set(values).size !== values.length) {
      this.fail(path, "expected_unique_values");
    }
  }

  equal(actual: string | number, expected: string | number, path: string): void {
    if (actual !== expected) {
      this.fail(path, `identity_mismatch_expected_${expected}`);
    }
  }

  nonDecreasing(values: number[], path: string): void {
    for (let index = 1; index < values.length; index += 1) {
      if ((values[index] as number) < (values[index - 1] as number)) {
        this.fail(`${path}[${index}]`, "expected_non_decreasing_order");
      }
    }
  }

  range(start: number, end: number, path: string, maximum?: number): void {
    if (end < start) {
      this.fail(path, "range_end_before_start");
    }
    if (maximum !== undefined && end > maximum) {
      this.fail(path, `range_exceeds_maximum_${maximum}`);
    }
  }
}
