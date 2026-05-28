# packages/wal-cli/src/wal_cli/config/util.py

from typing import get_args, get_origin

from pydantic import BaseModel


def format_model_structure(model: BaseModel, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent

    for field_name, field_info in model.__class__.model_fields.items():
        field_type = field_info.annotation
        lines.append(f"{prefix}- {field_name}")

        # Handle direct BaseModel subclasses
        if field_type is not None and hasattr(field_type, "__bases__") and issubclass(field_type, BaseModel):
            nested_model = field_type.model_construct()
            nested_structure = format_model_structure(nested_model, indent + 1)
            lines.append(nested_structure)
        # Handle generic types like dict[K, V] or list[T]
        elif field_type is not None:
            origin = get_origin(field_type)
            args = get_args(field_type)

            if origin is not None and args:
                # Check if any type arguments are BaseModel subclasses
                for arg in args:
                    if hasattr(arg, "__bases__") and issubclass(arg, BaseModel):
                        nested_model = arg.model_construct()
                        nested_structure = format_model_structure(nested_model, indent + 1)
                        lines.append(nested_structure)
                        break

            # Always show the type annotation
            type_str = str(field_type).replace("typing.", "")
            lines.append(f"{prefix}  {field_name}: {type_str}")

    return "\n".join(lines)
