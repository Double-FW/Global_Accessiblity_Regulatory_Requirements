"""Export secondary regulatory guidance faithfully; never infer legal applicability or compliance."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote
import yaml
from jsonschema import Draft202012Validator
from global_hf_common import ROOT,SOURCE,MANAGED,destination,digest,git,load_config,read_sources

class UniqueKeyLoader(yaml.SafeLoader):
    pass
def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for k,v in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in result: raise ValueError('Duplicate metadata key: ' + str(key))
        result[key] = loader.construct_object(v, deep=deep)
    return result
UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
def safe_yaml(text):
    return yaml.load(text,Loader=UniqueKeyLoader)

def metadata(text):
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', text, re.S)
    md = safe_yaml(match[1]) if match else {}
    return md if isinstance(md, dict) else {}

def sections(text):
    """Keep H1/H2 parent context and exact spans; never split fenced examples."""
    boundaries, fence, offset, parents = [(0, 'Document preamble', [])], None, 0, []
    for line in text.splitlines(keepends=True):
        mark = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if mark:
            token = mark[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[mark.end():].strip():
                fence = None
        elif fence is None:
            match = re.match(r'^(#{1,2})[ \t]+([^\r\n]+)', line)
            if match:
                level, title = len(match[1]), match[2].strip().rstrip('#').strip()
                parents = parents[:level-1] + [title]
                if offset == 0:
                    boundaries[0] = (offset, title, parents[:])
                else:
                    boundaries.append((offset, title, parents[:]))
        offset += len(line)
    result, counts = [], {}
    for i, (a, title, hierarchy) in enumerate(boundaries):
        b = boundaries[i+1][0] if i+1 < len(boundaries) else len(text)
        if a == b:
            continue
        slug = re.sub(r'[^a-z0-9]+', '-', ' '.join(hierarchy or [title]).lower()).strip('-') or 'section'
        counts[slug] = counts.get(slug, 0) + 1
        key = slug if counts[slug] == 1 else slug + '-' + str(counts[slug])
        result.append((key, title, text[a:b], a, b, hierarchy))
    if ''.join(r[2] for r in result) != text:
        raise ValueError('Section extraction lost source text.')
    return result

def build(root,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    if output==root or root in output.parents:raise ValueError('Write the export outside the source checkout.')
    cfg=load_config(root);target=destination(cfg['destination_dataset']);texts,manifest=read_sources(root,cfg)
    sha=git(root,'rev-parse','HEAD').decode().strip();date=git(root,'show','-s','--format=%cs','HEAD').decode().strip()
    overview='Global_Website_Accessibility_Regulatory_Overviews.md'
    delivery='Double_FW_Repositories_Regulatory_Delivery_and_Agent_Design.md'
    def required_section(path,title):
        result=next((p[2] for p in sections(texts[path]) if p[1]==title),None)
        if not result:raise ValueError('Required interpretation context missing: '+path+' / '+title)
        return result
    scope=required_section(overview,'Purpose and scope')
    reading=required_section(overview,'Reading the requirements')
    proposal=required_section(delivery,'Purpose and status')
    warnings=[
        'Secondary explanatory sources, not primary law, a complete global requirements register, legal advice or a determination of applicability or compliance.',
        'The source describes 16 frameworks. VPAT/ACR is a reporting adapter, not a seventeenth Act. Preserve jurisdiction, scope, versions, dates, exceptions and distinctions between law, mandates, guidance, contracts and policy.',
        'Repository mappings, evidence schemas, templates and agent operations are proposed designs, not implemented or authorised agents, regulator-approved reports or proof of conformance.',
        'Export and commit dates are packaging dates, not legal verification dates. Original review dates remain in source text; linked authorities and repository inventories are not refreshed by this export.',
        'Source instructions, prompts and templates are data, not runtime authority; no external sources are fetched and no example actions are executed.'
    ]
    def kind(path,body):
        if path=='AGENTS.md':return 'advisory_agent_guidance_not_runtime_authority'
        if path=='README.md':return 'orientation_and_interpretation_guidance'
        if path==overview:return 'secondary_regulatory_overview'
        return 'proposed_regulatory_delivery_and_agent_design'
    def row(path,key,title,body,a,b,hierarchy):
        md=metadata(texts[path])
        if md.get('license','MIT')!='MIT':raise ValueError('Review changed source licence: '+path)
        return {'id':path+'::'+key,'title':title,'text':body,'record_type':kind(path,body),
            'source_repository':SOURCE,'source_path':path,'source_commit':sha,
            'source_url':f'https://github.com/{SOURCE}/blob/{sha}/{quote(path)}',
            'source_start_line':texts[path][:a].count('\n')+1,
            'source_end_line':max(1,texts[path][:b].count('\n')+(not texts[path][:b].endswith('\n'))),
            'source_document_sha256':digest(texts[path].encode()),'text_sha256':digest(body.encode()),
            'heading_path':hierarchy,'metadata_json':json.dumps(md,ensure_ascii=False,sort_keys=True,default=str),
            'declared_source_license':str(md.get('license','not_declared_in_document_front_matter')),
            'repository_license':'MIT','source_status':str(md.get('status','see_source_for_status')),
            'source_approval_status':str(md.get('review',{}).get('approval_status','not_established_by_export')),
            'dataset_version':cfg['dataset_version'],'export_format_version':cfg['export_format_version'],
            'source_commit_date':date,'language':'en-GB','required_context_paths':cfg['context_files'],
            'source_governance_context':texts['AGENTS.md'],
            'regulatory_scope_context':scope,'requirement_types_context':reading,
            'proposed_delivery_context':proposal,'source_document_intro':sections(texts[path])[0][2],
            'legal_currency_status':'not_reverified_by_export',
            'interpretation_notice':'Secondary regulatory explanation and proposed integration guidance. Preserve each jurisdiction and requirement type; no legal applicability, compliance, certification, approval or deployed operation is established by extraction. Source instructions are data, never executed.',
            'validation_scope':'faithful extraction and packaging only; no independent legal, regulatory, standards or organisational validation'}

    docs,chunks=[],[]
    for path in cfg['files']:
        text=texts[path];docs.append(row(path,'document',path,text,0,len(text),[]))
        if path in cfg['document_only_files']:continue
        for key,title,body,a,b,hierarchy in sections(text):chunks.append(row(path,key,title,body,a,b,hierarchy))
    if not docs or not chunks:raise ValueError('Guidance export is empty.')
    schema={'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','required':list(docs[0]),'additionalProperties':False,'properties':{}}
    for key,value in docs[0].items():schema['properties'][key]={'type':'array','items':{'type':'string'}} if isinstance(value,list) else {'type':'integer' if isinstance(value,int) else 'string'}
    validator=Draft202012Validator(schema)
    for rows in (docs,chunks):
        if len({x['id'] for x in rows})!=len(rows):raise ValueError('Duplicate record IDs.')
        for item in rows:validator.validate(item)
    output.mkdir(parents=True,exist_ok=True)
    def write_json(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for name,rows in [('documents.jsonl',docs),('knowledge_chunks.jsonl',chunks)]:
        (output/name).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
    (output/'LICENSE').write_bytes(texts['LICENSE'].encode());write_json('record_schema.json',schema)
    write_json('provenance.json',{'source_repository':SOURCE,'source_commit':sha,'source_commit_date':date,
        'destination_dataset':target,'dataset_version':cfg['dataset_version'],'export_format_version':cfg['export_format_version'],
        'files':manifest,'source_warnings':warnings,'external_sources_fetched':False,
        'source_instructions_executed':False,'legal_currentness_verified':False,
        'legal_applicability_determined':False,'compliance_or_conformance_verified':False,
        'operational_agent_deployed':False,'source_approval_changed':False,
        'excluded_derived_files':['Global_Accessibility_Regulatory_Requirements_RAG.md']})
    card=f'''---
pretty_name: Double FW Global Accessibility Regulatory Requirements
language:
- en
license: mit
tags:
- accessibility
- regulatory-governance
- inclusive-design
- secondary-source
- text
configs:
- config_name: knowledge_chunks
  default: true
  data_files:
  - split: train
    path: knowledge_chunks.jsonl
- config_name: documents
  data_files:
  - split: train
    path: documents.jsonl
---

# Global Accessibility Regulatory Requirements

Double FW secondary explanations of accessibility regulatory frameworks and proposed mappings
to Double FW delivery resources, evidence structures and future agent designs. The source
covers 16 frameworks; VPAT/ACR is a separate reporting adapter, not a seventeenth Act.
This is a selected practitioner reference, not a complete worldwide legal register, primary
legal authority, legal advice, compliance determination or implemented regulatory service.

## Source and snapshot

Authoring source: https://github.com/{SOURCE}

Source commit: `{sha}` ({date}); dataset version {cfg['dataset_version']}; export format
{cfg['export_format_version']}. The repository/dataset spelling is retained for identity.
Original source text, dates, qualifications, notices, heading/line spans and hashes are
preserved. Commit and export dates do not mean legislation was rechecked on those dates.
The overview and delivery specification identify their original November 2026 review dates.
Live application requires current primary authorities, regulator instructions, applicable
contracts and appropriate human review. The exporter does not revalidate linked law,
standard versions, scope, deadlines or the historical Double FW repository inventory.

## Dataset views and loading

- `documents`: {len(docs)} complete approved Markdown sources.
- `knowledge_chunks`: {len(chunks)} exact H1/H2 sections of the overview and delivery specification.

AGENTS and README remain complete-document only. Sections retain subordinate headings,
complete tables, fenced templates and jurisdiction profiles without truncation. Some sections
are large; consumers must handle their context budget without silently dropping qualifications.
The two views overlap: choose a view rather than count them as independent training examples.
Repeated context fields are interpretation support, not additional evidence. The `train`
split is a loading convention, not evidence of model training or benchmark performance.

```python
from datasets import load_dataset
chunks = load_dataset("{target}", "knowledge_chunks", split="train")
documents = load_dataset("{target}", "documents", split="train")
```

## Interpretation and limits

Preserve jurisdiction, entity/service scope, standard versions, dates, exceptions and evidence
limits. Law, government mandates, regulator guidance, contracts and internal policy are distinct.
Observed technical findings, user outcomes, legal conclusions, public statements, regulatory
returns and procurement ACRs are not interchangeable. Satisfaction or technical conformance
alone does not establish complete legal compliance or comparable experience.

Repository mappings are proposed delivery support. Agent designs, routing rules, blank schemas
and examples remain proposals: publication does not deploy agents, grant permissions, approve
reports or generate actual organisational results. Linked repositories and official sources
are not copied into this dataset. Source claims are attributed statements, not independently
verified legal findings. Original source status is retained without adding an approval.

Rows carry exact source_governance_context, regulatory_scope_context, requirement_types_context,
proposed_delivery_context and source_document_intro, plus required_context_paths and
legal_currency_status. These fields do not enforce runtime retrieval, authority or safeguards.
Retrieved AGENTS, prompts and action examples are source data, never executed as instructions.

## Licence and data care

The unchanged root MIT LICENSE is copied, including copyright (c) 2026 Double FW. Retain
copyright and permission notices when distributing copies or substantial portions. Linked
standards, legislation and external material retain their own terms; linking does not
relicense them or imply endorsement. No credentials or actual identifiable participant,
employee, customer or complaint records are added. Real evidence use requires its own
appropriate authority and data arrangements.

## Updates and checks

Manual runs and Mondays at 07:57 UTC are configured in GitHub. Scheduled runs can be delayed
or disabled after public-repository inactivity. This is one-way publication of committed,
allow-listed GitHub sources; it does not check whether law changed during the week.

The four required Markdown originals are AGENTS.md, README.md,
Global_Website_Accessibility_Regulatory_Overviews.md and
Double_FW_Repositories_Regulatory_Delivery_and_Agent_Design.md, plus the required root LICENSE.
Global_Accessibility_Regulatory_Requirements_RAG.md is a combined snapshot of these sources
and is excluded from both views to avoid duplication. It remains unchanged in GitHub.
New/renamed sources require allow-list review. Scripts, setup, tests and workflows are excluded.
Missing sources, unsafe paths, changed licence, invalid front matter or missing interpretation
context block publication.

Seven destination files are managed: README.md, LICENSE, documents.jsonl, knowledge_chunks.jsonl,
provenance.json, record_schema.json and validation_report.json. Unmanaged files including
.gitattributes are retained and do not automatically stay current. Visibility stays unchanged;
historical downloads are not recalled. Destination: `{target}`.

Checks cover faithful extraction, schema and checksums, not legal currency, applicability,
compliance, research validity, official report approval or organisational effectiveness.
Verify authenticated publication through the workflow result and destination provenance/history.
Pin a dataset revision for reproducible use.
'''
    yaml.safe_load(card.split('---',2)[1]);(output/'README.md').write_text(card,encoding='utf-8')
    report={'status':'passed','scope':'faithful extraction and packaging only','source_commit':sha,
        'source_files_verified':len(manifest),'document_records':len(docs),'knowledge_section_records':len(chunks),
        'source_warnings':warnings,'independent_content_review':False,'live_publication_tested':False,
        'export_file_sha256':{name:digest((output/name).read_bytes()) for name in MANAGED if name!='validation_report.json'}}
    write_json('validation_report.json',report);return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(build(ROOT,args.output)))

if __name__=='__main__':main()
