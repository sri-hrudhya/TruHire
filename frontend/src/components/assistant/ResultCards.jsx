import { formatIst } from '../../lib/datetime';

// The structured result a reply can carry (lists of candidates, demands, history, and the confirm card for an action).
export default function ResultCards({ data, index, expanded: openClients, onToggle, onPrefill, onDecide, deciding }) {
  return (
    <>
                  {data?.action === 'confirm_action' && data.pending && (
                    <div className="assistant-confirm" role="group" aria-label="Confirm action">
                      <h4 className="assistant-card-title">Confirm this action</h4>
                      <strong>{data.pending.summary}</strong>
                      {data.pending.decision
                        ? <small>{data.pending.decision === 'approve' ? 'Confirmed' : 'Cancelled'}</small>
                        : <span className="cluster cluster-tight">
                          <button type="button" className="btn btn-primary btn-compact" disabled={deciding} onClick={() => onDecide(index, data.pending, true)}>Confirm</button>
                          <button type="button" className="btn btn-secondary btn-compact" disabled={deciding} onClick={() => onDecide(index, data.pending, false)}>Cancel</button>
                        </span>}
                    </div>
                  )}
                  {data?.action === 'matches' && (
                    <div className="truhire-assistant-results"><h4 className="assistant-card-title">Best-match candidates · {data.position.display_id} ({data.position.no_of_positions} open)</h4>{data.results.slice(0, data.position.no_of_positions).map((row, i) => <div key={row.candidate?.id || i}><b>{i + 1}. {row.candidate?.candidate_name || row.candidate_name}</b> <span>{typeof row.match_score === 'number' ? `${row.match_score.toFixed(1)}%` : ''}</span></div>)}</div>
                  )}
                  {data?.action === 'client_candidate_matches' && (data.client_groups || []).map((group) => (
                    <section className="truhire-assistant-client-requirements" key={group.position.id}>
                      <h4 className="assistant-card-title">Candidates for requirement</h4>
                      <strong>{group.position.title}</strong><small>{group.position.client_name} · {group.total_matches} matches</small>
                      {group.results.map((row) => <a key={row.candidate.id} href={`/candidates/${row.candidate.id}`}>
                        <b>{row.candidate.candidate_name}</b><small>{typeof row.match_score === 'number' ? `${row.match_score.toFixed(1)}% match` : 'Open candidate profile'}</small>
                      </a>)}
                      {!group.results.length && <span>No candidates matched this requirement.</span>}
                    </section>
                  ))}
                  {data?.action === 'candidate_history' && <div className="truhire-assistant-results">
                    <h4 className="assistant-card-title">Candidate history</h4>
                    <a href={`/candidates/${data.candidate_id}`}><b>{data.candidate_display_id} · {data.candidate_name}</b><small>Open full candidate history</small></a>
                    {!!data.requirements?.length && <h4 className="assistant-card-title">Submitted to - current status</h4>}
                    {(data.requirements || []).map((item) => <div key={item.id}><b>{item.client_name || item.title} - {item.status}</b><small>{[item.last_modified && `Last modified ${formatIst(item.last_modified)}`, item.modified_by && `Modified by ${item.modified_by}`].filter(Boolean).join(' | ')}</small></div>)}
                    {!!data.items?.length && <h4 className="assistant-card-title">Notes</h4>}
                    {data.items.map((event, i) => <div key={`${event.timestamp}-${i}`}><b>{event.summary}</b><small>{[`Last modified ${formatIst(event.timestamp)}`, event.actor && `Modified by ${event.actor}`].filter(Boolean).join(' | ')}</small></div>)}
                  </div>}
                  {data?.action === 'open_positions' && data.requirements?.length > 0 && <div className="truhire-assistant-results">
                    <h4 className="assistant-card-title">Open positions</h4>
                    {data.requirements.slice(0, 10).map((item) => <div key={item.id}><b>{item.display_id} · {item.title}</b><small>{[item.client_name, `${item.no_of_positions ?? 'Not recorded'} open position${item.no_of_positions === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}</small></div>)}
                  </div>}
                  {data?.action === 'candidate_comparison' && <div className="truhire-assistant-results">
                    <h4 className="assistant-card-title">Candidate comparison</h4>
                    {data.candidates.map((candidate) => <a key={candidate.id} href={`/candidates/${candidate.id}`}>
                      <b>{candidate.display_id} · {candidate.name}</b>
                      <small>{candidate.years_experience ?? 'Experience not recorded'} years · {candidate.status}</small>
                      <small>Skills: {candidate.skills.join(', ') || 'Not recorded'}</small>
                    </a>)}
                  </div>}
                  {data?.action === 'candidate_lookup' && <div className="truhire-assistant-results">
                    <h4 className="assistant-card-title">Matching candidates</h4>
                    {data.results.map((candidate) => <a key={candidate.id} href={`/candidates/${candidate.id}`}>
                      <b>{candidate.display_id} · {candidate.candidate_name}</b>
                      <small>{[candidate.current_company, candidate.email, candidate.phone, candidate.status].filter(Boolean).join(' · ')}</small>
                    </a>)}
                  </div>}
                  {data?.action === 'email' && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/email?position=${data.position_id}`; }}>Open Email drafts</button>}
                  {data?.action === 'created' && data.position?.id && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/requirements?id=${data.position.id}`; }}>Open this demand</button>}
                  {data?.action === 'choose_position' && data.positions?.length > 0 && (
                    <div className="truhire-assistant-results">
                      {data.positions.slice(0, 8).map((position) => (
                        <button key={position.id} type="button" className="btn btn-secondary assistant-action" onClick={() => onPrefill(`What JD fields are present or missing for ${position.display_id}?`)}>
                          {position.display_id} · {position.title}
                        </button>
                      ))}
                    </div>
                  )}
                  {(data?.action === 'client_groups' || data?.action === 'client_demands') && (
                    <div className="truhire-assistant-client-groups">
                      {(data.clients || [{ name: data.client_name, requirements: data.requirements || [], count: (data.requirements || []).length }]).map((client) => {
                        const expanded = data.action === 'client_demands' || openClients[`${index}:${client.name}`];
                        return (
                          <section key={client.name} className="truhire-assistant-client-group">
                            <button type="button" className="truhire-assistant-client-toggle" onClick={() => onToggle(`${index}:${client.name}`)} aria-expanded={expanded}>
                              <strong>{client.name}</strong><span>{client.count ?? client.requirements.length} {(client.count ?? client.requirements.length) === 1 ? 'demand' : 'demands'}</span>
                            </button>
                            {expanded && <div className="truhire-assistant-client-requirements">
                              {client.requirements.map((requirement) => {
                                const clientParam = requirement.client_name?.trim() ? requirement.client_name : '__unassigned__';
                                const query = new URLSearchParams();
                                if (requirement.demand_id) query.set('demand', requirement.demand_id);
                                query.set('client', clientParam);
                                return <a key={requirement.id} href={`/requirements?${query}`}><b>{requirement.display_id || 'JD'}</b> · {requirement.title}<small>{requirement.demand_name || 'No practice assigned'}</small></a>;
                              })}
                              {!client.requirements.length && <span>No demands found for this client.</span>}
                            </div>}
                          </section>
                        );
                      })}
                    </div>
                  )}
                  {data?.field_report && (
                    <div className="truhire-assistant-results truhire-assistant-field-report">
                      <strong>Here’s what I could read from the document</strong>
                      {data.field_report.present.length
                        ? data.field_report.present.map((field) => <div key={field.name}><b>{field.name}:</b> {field.value}</div>)
                        : <div>No structured fields could be confirmed from the document.</div>}
                      <div><b>Not stated in the document:</b> {data.field_report.missing.join(', ') || 'None'}</div>
                    </div>
                  )}
    </>
  );
}
