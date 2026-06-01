# DocTransAI

DocTransAI is a template-driven document transformation project. It ingests structured document bundles, maps source evidence into target templates, and renders traceable output documents.

The project keeps its runtime isolated from DataProxy. DataProxy v0 data-asset schemas are vendored as a local contract snapshot under `contracts/dataproxy/data_asset_pack_v0/`, and DocTransAI reads `parsed_document_bundle.json` through its own `doctransai.data_layer` package.
