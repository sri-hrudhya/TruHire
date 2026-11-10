// How each requirement review status is drawn: a mark, not a coloured pill.
//   hollow = still to decide, filled = shortlisted, struck = not shortlisted.
export const STATUS_MARKS = Object.freeze({
  New: 'hollow',
  Mapped: 'filled',
  Shortlisted: 'filled',
  Interviewed: 'filled',
  Rejected: 'struck',
});

export const markFor = (status) => STATUS_MARKS[status] || 'hollow';
