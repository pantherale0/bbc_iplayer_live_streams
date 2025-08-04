"""Amis admin."""

from typing import List
from fastapi import Request

from fastapi_amis_admin import admin
from fastapi_amis_admin.admin import AdminApp
from fastapi_amis_admin.amis import (
    Page,
    PageSchema,
    TableColumn,
    TableCRUD,
)
from fastapi_amis_admin.crud.schema import (
    BaseApiOut,
    Paginator,
)
from fastapi_amis_admin.models.fields import Field
from fastapi_amis_admin.utils.pydantic import (
    model_fields,
)
from . import _CATEGORIES, _PROGRAMMES

class BBCAdmin(admin.PageAdmin):
    page_schema = PageSchema(label="BBC iPlayer", icon="fa fa-tv")
    page_path = "/"
    router_prefix = "/bbc"
    paginator=Paginator(perPageMax=100)

    class ProgrammeModel(BaseApiOut):
        id: str = Field(..., title="ID")
        title: str = Field(..., title="Title")

        @classmethod
        def parse_programme(cls, programme: dict):
            return programme and cls(**{k: getattr(programme, k, None) for k in model_fields(cls)})


    @classmethod
    def bind(cls, app: AdminApp) -> "BBCAdmin":
        app.register_admin(cls)
        return cls(app)

    async def get_page(self, request: Request) -> Page:
        page = await super().get_page(request)
        headerToolbar = [
            "reload",
            "bulkActions",
            {"type": "columns-toggler", "align": "right"},
            {"type": "drag-toggler", "align": "right"},
            {"type": "pagination", "align": "right"},
            {
                "type": "tpl",
                "tpl": "SHOWING ${items|count} OF ${total} RESULT(S)",
                "className": "v-middle",
                "align": "right",
            },
        ]
        page.body = TableCRUD(
            api=f"get:{self.router_path}/programmes",
            autoFillHeight=True,
            headerToolbar=headerToolbar,
            filterTogglable=True,
            filterDefaultVisible=False,
            syncLocation=False,
            keepItemSelectionOnPageChange=True,
            footerToolbar=[
                "statistics",
                "switch-per-page",
                "pagination",
                "load-more",
                "export-csv",
            ],
            columns=await self.get_list_columns(request),
        )
        return page

    async def get_list_columns(self, request: Request) -> List[TableColumn]:
        columns = []
        for modelfield in model_fields(self.ProgrammeModel).values():
            column  = self.site.amis_parser.as_table_column(modelfield, False)
            if column:
                columns.append(column)
        return columns
