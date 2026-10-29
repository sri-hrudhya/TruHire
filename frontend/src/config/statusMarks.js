// How each requirement review status is drawn: a mark, not a coloured pill.
//   hollow = still to decide, filled = shortlisted, struck = not shortlisted.
export const STATUS_MARKS = Object.freeze({
  'Pending Review': 'hollow',
  Shortlisted: 'filled',
  'Not Shortlisted': 'struck',
});

export const markFor = (status) => STATUS_MARKS[status] || 'hollow';
