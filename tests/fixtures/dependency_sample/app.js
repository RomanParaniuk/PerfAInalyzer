// Fixture for the dependency-footprint stage: two date libraries doing the same job,
// a heavy client constructed at module load, a whole-package utility import, and a
// declared dependency (left-pad) that is never imported.
import moment from "moment";
import { format } from "date-fns";
import _ from "lodash";
import AWS from "aws-sdk";

const s3 = new AWS.S3();

export function stamp(date) {
  return `${format(date, "yyyy-MM-dd")} (${moment(date).fromNow()})`;
}

export function keyed(rows) {
  return _.keyBy(rows, "id");
}

export async function fetchReport(bucket, key) {
  return s3.getObject({ Bucket: bucket, Key: key }).promise();
}
