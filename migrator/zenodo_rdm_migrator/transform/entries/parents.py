# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 CERN.
#
# ZenodoRDM is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Zenodo migrator parent record transformer entries."""


from invenio_rdm_migrator.transform import Entry

from ...errors import NoConceptRecidForDraft

ZENODO_DATACITE_PREFIXES = (
    "10.5281/",
    "10.5072/",  # Test DOI prefix, useful for tests
)

IGNORED_COMMUNITIES = (
    "zenodo",
    "ecfunded",
)


class ParentRecordEntry(Entry):
    """Parent record transform entry class."""

    def _schema(self, entry):
        """Return JSONSchema of the parent."""
        return "local://records/parent-v3.0.0.json"

    def _created(self, entry):
        """Returns the creation date of the record."""
        return entry["created"]

    def _updated(self, entry):
        """Returns the creation date of the record."""
        return entry["updated"]

    def _version_id(self, entry):
        """Returns the version id of the record."""
        return entry["version_id"]

    def _communities(self, entry):
        result = {}
        communities = entry["json"].get("communities")
        if communities:
            slugs = [slug for slug in communities if slug not in IGNORED_COMMUNITIES]
            result["ids"] = slugs
            # If there's only one community, we set it as the default also
            if len(slugs) == 1:
                result["default"] = slugs[0]
            else:
                result["default"] = None
        return result

    def _pids(self, entry):
        pids = {}

        is_draft = "deposits" in entry["json"]["$schema"]
        doi = entry["json"].get("doi")
        conceptdoi = entry["json"].get("conceptdoi")
        if doi and doi.startswith(ZENODO_DATACITE_PREFIXES):
            if conceptdoi:
                pids["doi"] = {
                    "client": "datacite",
                    "provider": "datacite",
                    "identifier": conceptdoi,
                }
            elif not is_draft:  # old Zenodo DOI record without concept DOI
                pids["doi"] = {"provider": "legacy", "identifier": ""}
        return pids

    def transform(self, entry):
        """Transform a parent."""
        transformed = {}
        # both created and updated are the same as the record
        self._load_partial(entry, transformed, ["created", "updated", "version_id"])

        # We "manually" handle partial data for the JSON field
        if "json" in entry:
            # check if conceptrecid exists and bail otherwise. should not happen!
            # this is the case for some deposits and they should be fixed in prod as it
            parent_pid = entry["json"].get("conceptrecid")
            if not parent_pid:
                # we raise so the error logger writes these cases in the log file
                raise NoConceptRecidForDraft(draft=entry)

            communities = self._communities(entry)
            transformed["json"] = {
                # loader is responsible for creating/updating if the PID exists.
                "$schema": self._schema(entry),
                "id": parent_pid,
                "communities": communities,
                "pids": self._pids(entry),
            }
            owners = entry["json"].get("owners") or []
            deposit_owners = entry["json"].get("_deposit", {}).get("owners") or []
            owner = next(iter(owners or deposit_owners), None)
            if owner is not None:
                transformed["json"].setdefault("access", {})
                transformed["json"]["access"] = {"owned_by": {"user": owner}}

            access_conditions = entry["json"].get("access_conditions")
            if access_conditions:
                transformed["json"].setdefault("access", {})
                transformed["json"]["access"]["settings"] = {
                    "allow_user_requests": True,
                    "allow_guest_requests": True,
                    "accept_conditions_text": access_conditions,
                    "secret_link_expiration": 30,
                }

        elif not self.partial:
            raise KeyError("json")
        # else, pass

        return transformed
