export function decimalPlaces(value: number): number {
  const [significand, exponent = '0'] = String(value).split('e');
  const fractionLength = significand.split('.')[1]?.length ?? 0;
  return Math.max(0, fractionLength - Number(exponent));
}
