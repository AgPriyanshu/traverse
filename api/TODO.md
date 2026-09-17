### TODO

- [x] Add Graph db setup
- [x] Setup langfuse traces
- [X] Download some books from japanese authors
- [x] Add chapter_id and chapter_title handling in the docling items, use docling heading items and small LLM like qwen3-4b-instruct to identify if it is a chapter
- [ ] Add character and relationship extraction
  - Need to extract the characters
  - I think I should do these in batches
  - I want to do batching based on the token
  - I will need to count the prompt and the chunks text to fit in the model and based on it

- [ ] Add next stage of parsing and finding nodes and create entry for Knowledge graph

### Technical Debts
- [ ] Create docker compose services for rabbit-mq and celery
- [ ] Add warmup code for Sentence Transformer
