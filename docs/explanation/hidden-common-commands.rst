.. _explanation-hidden-common-commands:

What are hidden and common commands?
=====================================

When preparing the automatic help messages Craft CLI will consider if a message is
common or hidden.

Common commands are those that surely the users will use more frequently and to be
learned first, and Craft CLI will list and describe shortly after the summary in the
full help.

Hidden commands, on the other hand, will not appear at all in the help messages (but
will just work if used), which is useful for deprecated commands (as they will disappear
in a near future they should not be advertised) or aliases (multiple commands with
different names but same functionality).
