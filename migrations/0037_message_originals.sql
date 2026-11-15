-- Approve and send (bl_122, decision 88; SPEC 23.3): a person's edit keeps the text the desk wrote, so the approval
-- sheet can restore one change at a time. Filled the first time a person changes a draft; null on a message nobody edited.
alter table messages
  add column original_subject text,
  add column original_body text;
