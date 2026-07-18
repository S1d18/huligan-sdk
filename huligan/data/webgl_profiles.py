"""
WebGL parameter profiles for Chrome/ANGLE/D3D11 on Windows.

Data source: Real Chrome 146 ANGLE output captured from NVIDIA GeForce GTX 1060 6GB.
Variations for Intel/AMD based on ANGLE D3D11 feature level differences.

These profiles are used to generate realistic webgl_param_* values in .conf files
so that every browser instance has a consistent WebGL fingerprint matching its GPU.

Key insight: On Chrome/ANGLE/D3D11, most GL parameters are IDENTICAL across all GPUs.
Only ~15 parameters actually vary, and most of those are capability limits.
Shader precision is always the same on D3D11 (feature level 11_0+).
"""

# =============================================================================
# GL Enum Name Mapping (for documentation / debugging)
# =============================================================================

GL_ENUM_NAMES = {
    # --- State variables (default values, not fingerprint-relevant) ---
    2849: "LINE_WIDTH",
    2884: "CULL_FACE",
    2885: "CULL_FACE_MODE",
    2886: "FRONT_FACE",
    2928: "DEPTH_RANGE",
    2929: "DEPTH_TEST",
    2930: "DEPTH_WRITEMASK",
    2931: "DEPTH_CLEAR_VALUE",
    2932: "DEPTH_FUNC",
    2960: "STENCIL_TEST",
    2961: "STENCIL_CLEAR_VALUE",
    2962: "STENCIL_FUNC",
    2963: "STENCIL_VALUE_MASK",
    2964: "STENCIL_FAIL",
    2965: "STENCIL_PASS_DEPTH_FAIL",
    2966: "STENCIL_PASS_DEPTH_PASS",
    2967: "STENCIL_REF",
    2968: "STENCIL_WRITEMASK",
    2978: "VIEWPORT",
    3024: "DITHER",
    3042: "BLEND",
    3074: "READ_BUFFER",
    3088: "SCISSOR_BOX",
    3089: "SCISSOR_TEST",
    3106: "COLOR_CLEAR_VALUE",
    3107: "COLOR_WRITEMASK",
    3314: "UNPACK_ROW_LENGTH",
    3315: "UNPACK_SKIP_ROWS",
    3316: "UNPACK_SKIP_PIXELS",
    3317: "UNPACK_ALIGNMENT",
    3330: "PACK_ROW_LENGTH",
    3331: "PACK_SKIP_ROWS",
    3332: "PACK_SKIP_PIXELS",
    3333: "PACK_ALIGNMENT",
    10752: "GENERATE_MIPMAP_HINT",
    32773: "BLEND_COLOR",
    32777: "BLEND_EQUATION_RGB",
    32823: "SAMPLE_COVERAGE_VALUE",
    32824: "SAMPLE_COVERAGE_INVERT",
    32926: "SAMPLE_ALPHA_TO_COVERAGE",
    32928: "SAMPLE_COVERAGE",

    # --- Framebuffer properties ---
    3408: "SUBPIXEL_BITS",
    3410: "RED_BITS",
    3411: "GREEN_BITS",
    3412: "BLUE_BITS",
    3413: "ALPHA_BITS",
    3414: "DEPTH_BITS",
    3415: "STENCIL_BITS",
    32936: "SAMPLES",
    32937: "SAMPLE_BUFFERS",

    # --- Capability limits (FINGERPRINT-RELEVANT) ---
    3379: "MAX_TEXTURE_SIZE",
    3386: "MAX_VIEWPORT_DIMS",
    7936: "VENDOR",
    7937: "RENDERER",
    7938: "VERSION",
    32873: "TEXTURE_BINDING_CUBE_MAP",
    32877: "DRAW_BUFFER0",
    32878: "DRAW_BUFFER1",
    32883: "MAX_3D_TEXTURE_SIZE",
    32938: "MAX_SAMPLES_ANGLE",  # ANGLE-specific
    32939: "RASTERIZER_DISCARD",
    32968: "TEXTURE_BINDING_2D_ARRAY",
    32969: "MAX_ARRAY_TEXTURE_LAYERS",  # Might be state
    32970: "MIN_PROGRAM_TEXEL_OFFSET",
    32971: "MAX_PROGRAM_TEXEL_OFFSET",
    33000: "MAX_ELEMENT_INDEX",
    33001: "MAX_SERVER_WAIT_TIMEOUT",  # WebGL2
    33170: "FRAGMENT_SHADER_DERIVATIVE_HINT",
    33901: "ALIASED_POINT_SIZE_RANGE",
    33902: "ALIASED_LINE_WIDTH_RANGE",
    34016: "ACTIVE_TEXTURE",
    34024: "MAX_RENDERBUFFER_SIZE",
    34045: "MAX_TEXTURE_LOD_BIAS",
    34047: "MAX_TEXTURE_MAX_ANISOTROPY_EXT",
    34068: "TEXTURE_BINDING_CUBE_MAP_POSITIVE_X",
    34076: "MAX_CUBE_MAP_TEXTURE_SIZE",
    34467: "COMPRESSED_TEXTURE_FORMATS",

    # --- Stencil back-face ---
    34816: "STENCIL_BACK_FUNC",
    34817: "STENCIL_BACK_FAIL",
    34818: "STENCIL_BACK_PASS_DEPTH_FAIL",
    34819: "STENCIL_BACK_PASS_DEPTH_PASS",

    # --- Draw buffers (WebGL2) ---
    34852: "MAX_DRAW_BUFFERS",
    34853: "DRAW_BUFFER0",
    34854: "DRAW_BUFFER1",
    34855: "DRAW_BUFFER2",
    34856: "DRAW_BUFFER3",
    34857: "DRAW_BUFFER4",
    34858: "DRAW_BUFFER5",
    34859: "DRAW_BUFFER6",
    34860: "DRAW_BUFFER7",

    # --- Blend equation ---
    34877: "BLEND_EQUATION_ALPHA",

    # --- Vertex/Fragment limits ---
    34921: "MAX_VERTEX_ATTRIBS",
    34930: "MAX_TEXTURE_IMAGE_UNITS",
    34964: "MAX_VERTEX_UNIFORM_VECTORS",  # Actually MAX_FRAGMENT_UNIFORM_COMPONENTS in some mappings
    34965: "MAX_VARYING_COMPONENTS",

    # --- WebGL2 capability limits ---
    35071: "MAX_ELEMENT_INDEX",  # WebGL2
    35076: "MIN_PROGRAM_TEXEL_OFFSET",
    35077: "MAX_PROGRAM_TEXEL_OFFSET",
    35371: "MAX_VARYING_COMPONENTS",
    35373: "MAX_VERTEX_OUTPUT_COMPONENTS",
    35374: "MAX_FRAGMENT_INPUT_COMPONENTS",
    35375: "MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS",
    35376: "MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS",
    35377: "MAX_UNIFORM_BUFFER_BINDINGS",  # Actually TRANSFORM_FEEDBACK_BUFFER_SIZE? Check
    35379: "MAX_UNIFORM_BLOCK_SIZE",
    35380: "MAX_COMBINED_VERTEX_UNIFORM_COMPONENTS",
    35657: "MAX_3D_TEXTURE_SIZE",  # WebGL2
    35658: "MAX_ELEMENTS_VERTICES",
    35659: "MAX_ELEMENTS_INDICES",
    35660: "MAX_VERTEX_TEXTURE_IMAGE_UNITS",  # Note: in WebGL1 too
    35661: "MAX_COMBINED_TEXTURE_IMAGE_UNITS",

    # --- Shader ---
    35723: "FRAGMENT_SHADER_DERIVATIVE_HINT",  # WebGL2
    35724: "SHADING_LANGUAGE_VERSION",
    35725: "CURRENT_PROGRAM",
    35738: "IMPLEMENTATION_COLOR_READ_TYPE",
    35739: "IMPLEMENTATION_COLOR_READ_FORMAT",

    # --- Transform feedback / Uniform buffer (WebGL2) ---
    35968: "MAX_TRANSFORM_FEEDBACK_SEPARATE_COMPONENTS",
    35977: "RASTERIZER_DISCARD",
    35978: "MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS",
    35979: "MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS",

    # --- Misc WebGL2 ---
    36003: "STENCIL_BACK_REF",
    36004: "STENCIL_BACK_VALUE_MASK",
    36005: "STENCIL_BACK_WRITEMASK",
    36063: "MAX_COLOR_ATTACHMENTS",
    36183: "MAX_SAMPLES",
    36203: "MAX_ELEMENT_INDEX",
    36345: "MAX_TEXTURE_MAX_ANISOTROPY_EXT",

    # --- More WebGL2 limits ---
    36347: "MAX_VERTEX_UNIFORM_VECTORS",
    36348: "MAX_VARYING_VECTORS",
    36349: "MAX_FRAGMENT_UNIFORM_VECTORS",

    # --- Sync/query ---
    36387: "TRANSFORM_FEEDBACK_ACTIVE",
    36388: "TRANSFORM_FEEDBACK_PAUSED",
    36392: "TRANSFORM_FEEDBACK_BINDING",
    36795: "MAX_DUAL_SOURCE_DRAW_BUFFERS",

    # --- WebGL2 misc ---
    37137: "COPY_READ_BUFFER_BINDING",
    37154: "MAX_VERTEX_UNIFORM_COMPONENTS",
    37157: "MAX_FRAGMENT_UNIFORM_COMPONENTS",

    # --- Pixel storage / misc ---
    37440: "UNPACK_FLIP_Y_WEBGL",
    37441: "UNPACK_PREMULTIPLY_ALPHA_WEBGL",
    37443: "UNPACK_COLORSPACE_CONVERSION_WEBGL",
    37444: "BROWSER_DEFAULT_WEBGL",
    37445: "UNMASKED_VENDOR_WEBGL",
    37446: "UNMASKED_RENDERER_WEBGL",
    37447: "COPY_WRITE_BUFFER_BINDING",

    38449: "MAX_CLIENT_WAIT_TIMEOUT_WEBGL",
}


# =============================================================================
# Shader Precision Formats — CONSTANT across all Chrome/ANGLE/D3D11
# =============================================================================
# On ANGLE/D3D11 (feature level 11_0), all precision qualifiers map to
# the same underlying D3D types, so these values are always identical.
#
# Key format: "shaderType,precisionType"
#   shaderType: 35633 = VERTEX_SHADER, 35632 = FRAGMENT_SHADER
#   precisionType: 36336=LOW_FLOAT, 36337=MEDIUM_FLOAT, 36338=HIGH_FLOAT,
#                  36339=LOW_INT, 36340=MEDIUM_INT, 36341=HIGH_INT

SHADER_PRECISION_D3D11 = {
    # Vertex shader
    "35633,36336": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # LOW_FLOAT
    "35633,36337": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # MEDIUM_FLOAT
    "35633,36338": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # HIGH_FLOAT
    "35633,36339": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # LOW_INT
    "35633,36340": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # MEDIUM_INT
    "35633,36341": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # HIGH_INT
    # Fragment shader
    "35632,36336": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # LOW_FLOAT
    "35632,36337": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # MEDIUM_FLOAT
    "35632,36338": {"rangeMin": 127, "rangeMax": 127, "precision": 23},  # HIGH_FLOAT
    "35632,36339": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # LOW_INT
    "35632,36340": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # MEDIUM_INT
    "35632,36341": {"rangeMin": 31, "rangeMax": 30, "precision": 0},     # HIGH_INT
}


# =============================================================================
# WebGL Extensions — by GPU vendor (Chrome/ANGLE/D3D11 on Windows)
# =============================================================================
# Captured from real Chrome 146. Some extensions are vendor-specific.

WEBGL1_EXTENSIONS_COMMON = [
    "ANGLE_instanced_arrays",
    "EXT_blend_minmax",
    "EXT_clip_control",
    "EXT_color_buffer_half_float",
    "EXT_depth_clamp",
    "EXT_disjoint_timer_query",
    "EXT_float_blend",
    "EXT_frag_depth",
    "EXT_polygon_offset_clamp",
    "EXT_shader_texture_lod",
    "EXT_texture_compression_bptc",
    "EXT_texture_compression_rgtc",
    "EXT_texture_filter_anisotropic",
    "EXT_texture_mirror_clamp_to_edge",
    "EXT_sRGB",
    "KHR_parallel_shader_compile",
    "OES_element_index_uint",
    "OES_fbo_render_mipmap",
    "OES_standard_derivatives",
    "OES_texture_float",
    "OES_texture_float_linear",
    "OES_texture_half_float",
    "OES_texture_half_float_linear",
    "OES_vertex_array_object",
    "WEBGL_blend_func_extended",
    "WEBGL_color_buffer_float",
    "WEBGL_compressed_texture_s3tc",
    "WEBGL_compressed_texture_s3tc_srgb",
    "WEBGL_debug_renderer_info",
    "WEBGL_debug_shaders",
    "WEBGL_depth_texture",
    "WEBGL_draw_buffers",
    "WEBGL_lose_context",
    "WEBGL_multi_draw",
    "WEBGL_polygon_mode",
]

WEBGL2_EXTENSIONS_COMMON = [
    "EXT_clip_control",
    "EXT_color_buffer_float",
    "EXT_color_buffer_half_float",
    "EXT_conservative_depth",
    "EXT_depth_clamp",
    "EXT_disjoint_timer_query_webgl2",
    "EXT_float_blend",
    "EXT_polygon_offset_clamp",
    "EXT_render_snorm",
    "EXT_texture_compression_bptc",
    "EXT_texture_compression_rgtc",
    "EXT_texture_filter_anisotropic",
    "EXT_texture_mirror_clamp_to_edge",
    "EXT_texture_norm16",
    "KHR_parallel_shader_compile",
    "OES_draw_buffers_indexed",
    "OES_sample_variables",
    "OES_shader_multisample_interpolation",
    "OES_texture_float_linear",
    "WEBGL_blend_func_extended",
    "WEBGL_clip_cull_distance",
    "WEBGL_compressed_texture_s3tc",
    "WEBGL_compressed_texture_s3tc_srgb",
    "WEBGL_debug_renderer_info",
    "WEBGL_debug_shaders",
    "WEBGL_lose_context",
    "WEBGL_multi_draw",
    "WEBGL_polygon_mode",
    "WEBGL_provoking_vertex",
    "WEBGL_stencil_texturing",
]

# NVIDIA-specific extensions
WEBGL2_EXTENSIONS_NVIDIA = WEBGL2_EXTENSIONS_COMMON + [
    "NV_shader_noperspective_interpolation",
    "OVR_multiview2",
]

# Intel/AMD don't have NV_ extensions but may have OVR_multiview2
WEBGL2_EXTENSIONS_INTEL = WEBGL2_EXTENSIONS_COMMON + [
    "OVR_multiview2",
]

WEBGL2_EXTENSIONS_AMD = WEBGL2_EXTENSIONS_COMMON + [
    "OVR_multiview2",
]


# =============================================================================
# WebGL1 Parameters — Real Chrome/ANGLE/D3D11 values
# =============================================================================
# Captured from NVIDIA GeForce GTX 1060 6GB, Chrome 146.
# Parameters that are state variables (viewport, blend, etc.) use their
# default values. Fingerprinting scripts capture these defaults.

# Parameters CONSTANT across all Chrome/ANGLE/D3D11 GPUs (WebGL1)
WEBGL1_PARAMS_CONSTANT = {
    # State defaults
    2849: 1,                          # LINE_WIDTH
    2884: False,                      # CULL_FACE
    2885: 1029,                       # CULL_FACE_MODE (GL_BACK)
    2886: 2305,                       # FRONT_FACE (GL_CCW)
    2928: [0, 1],                     # DEPTH_RANGE
    2929: False,                      # DEPTH_TEST
    2930: True,                       # DEPTH_WRITEMASK
    2931: 1,                          # DEPTH_CLEAR_VALUE
    2932: 513,                        # DEPTH_FUNC (GL_LESS)
    2960: False,                      # STENCIL_TEST
    2961: 0,                          # STENCIL_CLEAR_VALUE
    2962: 519,                        # STENCIL_FUNC (GL_ALWAYS)
    2963: 4294967295,                 # STENCIL_VALUE_MASK
    2964: 7680,                       # STENCIL_FAIL (GL_KEEP)
    2965: 7680,                       # STENCIL_PASS_DEPTH_FAIL
    2966: 7680,                       # STENCIL_PASS_DEPTH_PASS
    2967: 0,                          # STENCIL_REF
    2968: 4294967295,                 # STENCIL_WRITEMASK
    3024: True,                       # DITHER
    3042: False,                      # BLEND
    3089: False,                      # SCISSOR_TEST
    3317: 4,                          # UNPACK_ALIGNMENT
    3333: 4,                          # PACK_ALIGNMENT
    3408: 4,                          # SUBPIXEL_BITS
    3410: 8,                          # RED_BITS
    3411: 8,                          # GREEN_BITS
    3412: 8,                          # BLUE_BITS
    3413: 8,                          # ALPHA_BITS
    3414: 24,                         # DEPTH_BITS
    3415: 0,                          # STENCIL_BITS
    7936: "WebKit",                   # VENDOR
    7937: "WebKit WebGL",             # RENDERER
    7938: "WebGL 1.0 (OpenGL ES 2.0 Chromium)",  # VERSION
    10752: 0,                         # GENERATE_MIPMAP_HINT
    32773: [0, 0, 0, 0],             # BLEND_COLOR
    32777: 32774,                     # BLEND_EQUATION_RGB (FUNC_ADD)
    32823: False,                     # SAMPLE_COVERAGE_VALUE
    32824: 0,                         # SAMPLE_COVERAGE_INVERT
    32926: False,                     # SAMPLE_ALPHA_TO_COVERAGE
    32928: False,                     # SAMPLE_COVERAGE
    32936: 1,                         # SAMPLES (default MSAA)
    32937: 4,                         # SAMPLE_BUFFERS
    32938: 1,                         # MAX_SAMPLES_ANGLE
    32939: False,                     # RASTERIZER_DISCARD
    32968: 0,                         # TEXTURE_BINDING_2D_ARRAY
    32969: 1,                         # possible state
    32970: 0,                         # state
    32971: 1,                         # state
    33170: 4352,                      # FRAGMENT_SHADER_DERIVATIVE_HINT (DONT_CARE)
    34016: 33984,                     # ACTIVE_TEXTURE (TEXTURE0)
    34467: [],                        # COMPRESSED_TEXTURE_FORMATS
    34816: 519,                       # STENCIL_BACK_FUNC (GL_ALWAYS)
    34817: 7680,                      # STENCIL_BACK_FAIL
    34818: 7680,                      # STENCIL_BACK_PASS_DEPTH_FAIL
    34819: 7680,                      # STENCIL_BACK_PASS_DEPTH_PASS
    34877: 32774,                     # BLEND_EQUATION_ALPHA (FUNC_ADD)
    35724: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)",
    35738: 5121,                      # IMPLEMENTATION_COLOR_READ_TYPE (UNSIGNED_BYTE)
    35739: 6408,                      # IMPLEMENTATION_COLOR_READ_FORMAT (RGBA)
    36003: 0,                         # STENCIL_BACK_REF
    36004: 4294967295,                # STENCIL_BACK_VALUE_MASK
    36005: 4294967295,                # STENCIL_BACK_WRITEMASK
    37440: False,                     # UNPACK_FLIP_Y_WEBGL
    37441: False,                     # UNPACK_PREMULTIPLY_ALPHA_WEBGL
    37443: 37444,                     # UNPACK_COLORSPACE_CONVERSION_WEBGL
}

# WebGL1 getParameter values. Like the WebGL2 table below, these are ANGLE-D3D11 constants - keep all
# classes identical (see the note on WEBGL2_PARAMS_BY_GPU). Only the renderer string differs by GPU.
# These are the only params that differ between GPU models on ANGLE/D3D11
WEBGL1_PARAMS_BY_GPU = {
    "nvidia_high": {
        # RTX 3070+ / RTX 40xx / RTX 50xx
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_TEXTURE_MAX_ANISOTROPY_EXT → actually 16 for most
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS (WebGL2 only in WGL1 context?)
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
    "nvidia_mid": {
        # GTX 1050-1660, RTX 2060-3060
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_TEXTURE_MAX_ANISOTROPY_EXT
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
    "intel_integrated": {
        # UHD 620/630/730/770, Iris Xe
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS (ANGLE-D3D11 const, all vendors)
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
    "amd_discrete": {
        # RX 5600-7900
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
    "amd_integrated": {
        # Vega 7/8/11, Radeon 660M/680M/780M
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS (ANGLE-D3D11 const, all vendors)
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
    "intel_discrete": {
        # Arc A580/A750/A770
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
    },
}


# =============================================================================
# WebGL2 Parameters — Real Chrome/ANGLE/D3D11 values
# =============================================================================

# Parameters CONSTANT across all Chrome/ANGLE/D3D11 GPUs (WebGL2)
# These include all WebGL1 constants (same defaults) plus WebGL2-specific
WEBGL2_PARAMS_CONSTANT = {
    # All WebGL1 state defaults carry over
    **{k: v for k, v in WEBGL1_PARAMS_CONSTANT.items()},

    # WebGL2 overrides/additions
    3074: 1029,                       # READ_BUFFER (GL_BACK)
    3314: 0,                          # UNPACK_ROW_LENGTH
    3315: 0,                          # UNPACK_SKIP_ROWS
    3316: 0,                          # UNPACK_SKIP_PIXELS
    3330: 0,                          # PACK_ROW_LENGTH
    3331: 0,                          # PACK_SKIP_ROWS
    3332: 0,                          # PACK_SKIP_PIXELS
    7938: "WebGL 2.0 (OpenGL ES 3.0 Chromium)",  # VERSION
    32877: 0,                         # DRAW_BUFFER0 (off)
    32878: 0,                         # DRAW_BUFFER1 (off)
    32883: 2048,                      # MAX_3D_TEXTURE_SIZE
    33000: 2147483647,                # MAX_ELEMENT_INDEX
    33001: 2147483647,                # MAX_SERVER_WAIT_TIMEOUT
    34045: 2,                         # MAX_SAMPLES (lower in WGL2 context)
    34852: 8,                         # MAX_DRAW_BUFFERS
    34853: 1029,                      # DRAW_BUFFER0 (GL_BACK)
    34854: 1029,                      # DRAW_BUFFER1
    34855: 1029,                      # DRAW_BUFFER2
    34856: 1029,                      # DRAW_BUFFER3
    34857: 1029,                      # DRAW_BUFFER4
    34858: 1029,                      # DRAW_BUFFER5
    34859: 1029,                      # DRAW_BUFFER6
    34860: 1029,                      # DRAW_BUFFER7
    35071: 2048,                      # MAX_ELEMENT_INDEX (WebGL2)
    35076: -8,                        # MIN_PROGRAM_TEXEL_OFFSET
    35077: 7,                         # MAX_PROGRAM_TEXEL_OFFSET
    35371: 12,                        # MAX_VARYING_COMPONENTS (12 = 4 varyings * 3 components)
    35373: 12,                        # MAX_VERTEX_OUTPUT_COMPONENTS
    35374: 24,                        # MAX_FRAGMENT_INPUT_COMPONENTS
    35375: 24,                        # MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS
    35376: 65536,                     # MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS
    35377: 212988,                    # MAX_UNIFORM_BUFFER_BINDINGS (or TRANSFORM_FEEDBACK related)
    35379: 200704,                    # MAX_UNIFORM_BLOCK_SIZE
    35380: 256,                       # MAX_COMBINED_VERTEX_UNIFORM_COMPONENTS
    35723: 4352,                      # FRAGMENT_SHADER_DERIVATIVE_HINT (DONT_CARE)
    35724: "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
    35968: 4,                         # MAX_TRANSFORM_FEEDBACK_SEPARATE_COMPONENTS
    35977: False,                     # RASTERIZER_DISCARD
    35978: 120,                       # MAX_TRANSFORM_FEEDBACK_INTERLEAVED_COMPONENTS
    35979: 4,                         # MAX_TRANSFORM_FEEDBACK_SEPARATE_ATTRIBS
    36063: 8,                         # MAX_COLOR_ATTACHMENTS
    36183: 8,                         # MAX_SAMPLES
    36203: 4294967294,                # MAX_ELEMENT_INDEX
    36387: False,                     # TRANSFORM_FEEDBACK_ACTIVE
    36388: False,                     # TRANSFORM_FEEDBACK_PAUSED
    37137: 0,                         # COPY_READ_BUFFER_BINDING
    37447: 0,                         # COPY_WRITE_BUFFER_BINDING
}

# WebGL2 getParameter values. These are ANGLE-D3D11 CONSTANTS: byte-identical across NVIDIA/Intel/AMD
# and integrated/discrete (confirmed via real captures, 2026-07). Keep every class IDENTICAL - only the
# renderer string differs. Do NOT re-introduce per-class variation (it is a coherence tell, not realism).
WEBGL2_PARAMS_BY_GPU = {
    "nvidia_high": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE (WebGL2)
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_TEXTURE_MAX_ANISOTROPY_EXT
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
    "nvidia_mid": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_TEXTURE_MAX_ANISOTROPY_EXT
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
    "intel_integrated": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
    "amd_discrete": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
    "amd_integrated": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
    "intel_discrete": {
        3379: 16384,                  # MAX_TEXTURE_SIZE
        3386: [32767, 32767],         # MAX_VIEWPORT_DIMS
        33901: [1, 1024],             # ALIASED_POINT_SIZE_RANGE
        33902: [1, 1],                # ALIASED_LINE_WIDTH_RANGE
        34024: 16384,                 # MAX_RENDERBUFFER_SIZE
        34076: 16384,                 # MAX_CUBE_MAP_TEXTURE_SIZE
        34921: 16,                    # MAX_VERTEX_ATTRIBS
        34930: 16,                    # MAX_TEXTURE_IMAGE_UNITS
        35657: 4096,                  # MAX_3D_TEXTURE_SIZE
        35658: 16380,                 # MAX_ELEMENTS_VERTICES
        35659: 120,                   # MAX_ELEMENTS_INDICES
        35660: 16,                    # MAX_VERTEX_TEXTURE_IMAGE_UNITS
        35661: 32,                    # MAX_COMBINED_TEXTURE_IMAGE_UNITS
        36347: 4095,                  # MAX_VERTEX_UNIFORM_VECTORS (4095*4=16380=COMPONENTS)
        36348: 30,                    # MAX_VERTEX_UNIFORM_BLOCKS
        36349: 1024,                  # MAX_FRAGMENT_UNIFORM_BLOCKS
        37154: 120,                   # MAX_VERTEX_UNIFORM_COMPONENTS
        37157: 120,                   # MAX_FRAGMENT_UNIFORM_COMPONENTS
    },
}


# =============================================================================
# Context Attributes — CONSTANT for Chrome/ANGLE/D3D11
# =============================================================================

CONTEXT_ATTRIBUTES = {
    "alpha": True,
    "antialias": True,
    "depth": True,
    "desynchronized": False,
    "failIfMajorPerformanceCaveat": False,
    "powerPreference": "default",
    "premultipliedAlpha": True,
    "preserveDrawingBuffer": False,
    "stencil": False,
    "xrCompatible": False,
}


# =============================================================================
# Fingerprint-critical params to write to .conf (subset for C++ patch)
# =============================================================================
# These are the ONLY WebGL parameters worth spoofing in C++.
# State variables don't need spoofing since they reset to same defaults.
# Vendor/renderer strings are already handled by patch 04.

FINGERPRINT_PARAMS = [
    3379,   # MAX_TEXTURE_SIZE
    3386,   # MAX_VIEWPORT_DIMS
    33901,  # ALIASED_POINT_SIZE_RANGE
    33902,  # ALIASED_LINE_WIDTH_RANGE
    34024,  # MAX_RENDERBUFFER_SIZE
    34076,  # MAX_CUBE_MAP_TEXTURE_SIZE
    34921,  # MAX_VERTEX_ATTRIBS
    34930,  # MAX_TEXTURE_IMAGE_UNITS
    35657,  # MAX_3D_TEXTURE_SIZE (WebGL2)
    35658,  # MAX_ELEMENTS_VERTICES (WebGL2)
    35659,  # MAX_ELEMENTS_INDICES (WebGL2)
    35660,  # MAX_VERTEX_TEXTURE_IMAGE_UNITS
    35661,  # MAX_COMBINED_TEXTURE_IMAGE_UNITS
    36347,  # MAX_VERTEX_UNIFORM_VECTORS
    36348,  # MAX_VERTEX_UNIFORM_BLOCKS (WebGL2)
    36349,  # MAX_FRAGMENT_UNIFORM_BLOCKS (WebGL2)
    37154,  # MAX_VERTEX_UNIFORM_COMPONENTS (WebGL2)
    37157,  # MAX_FRAGMENT_UNIFORM_COMPONENTS (WebGL2)
]


# =============================================================================
# Main API
# =============================================================================

def classify_gpu(renderer_string: str) -> str:
    """
    Classify a GPU renderer string into a profile category.

    Args:
        renderer_string: ANGLE renderer string or model name

    Returns:
        One of: "nvidia_high", "nvidia_mid", "intel_integrated",
                "intel_discrete", "amd_discrete", "amd_integrated"
    """
    r = renderer_string.upper()

    if "NVIDIA" in r:
        # High-end: RTX 3070+, RTX 40xx, RTX 50xx
        if any(x in r for x in [
            "RTX 5090", "RTX 5080", "RTX 5070",
            "RTX 4090", "RTX 4080", "RTX 4070",
            "RTX 3090", "RTX 3080", "RTX 3070",
        ]):
            return "nvidia_high"
        return "nvidia_mid"

    if "AMD" in r or "RADEON" in r:
        # Integrated: Vega, Radeon Graphics (no RX)
        if any(x in r for x in ["VEGA", "RADEON(TM)", "RADEON GRAPHICS", "680M", "660M", "780M"]):
            return "amd_integrated"
        return "amd_discrete"

    if "INTEL" in r:
        if any(x in r for x in ["ARC", "A770", "A750", "A580"]):
            return "intel_discrete"
        return "intel_integrated"

    # Default to nvidia_mid as most common
    return "nvidia_mid"


def get_webgl_params(renderer_string: str, webgl_version: int = 1) -> dict:
    """
    Get complete WebGL parameter set for a GPU.

    Args:
        renderer_string: ANGLE renderer string
        webgl_version: 1 or 2

    Returns:
        dict: All parameter values for this GPU/version combination
    """
    gpu_class = classify_gpu(renderer_string)

    if webgl_version == 2:
        params = dict(WEBGL2_PARAMS_CONSTANT)
        params.update(WEBGL2_PARAMS_BY_GPU.get(gpu_class, WEBGL2_PARAMS_BY_GPU["nvidia_mid"]))
    else:
        params = dict(WEBGL1_PARAMS_CONSTANT)
        params.update(WEBGL1_PARAMS_BY_GPU.get(gpu_class, WEBGL1_PARAMS_BY_GPU["nvidia_mid"]))

    return params


def get_fingerprint_params(renderer_string: str) -> dict:
    """
    Get only the fingerprint-critical WebGL params for .conf generation.
    Returns params as webgl_param_{enum} keys suitable for .conf output.

    Args:
        renderer_string: ANGLE renderer string

    Returns:
        dict: {3379: 16384, 3386: [32767, 32767], ...}
    """
    gpu_class = classify_gpu(renderer_string)
    gpu_params = WEBGL2_PARAMS_BY_GPU.get(gpu_class, WEBGL2_PARAMS_BY_GPU["nvidia_mid"])

    result = {}
    for enum in FINGERPRINT_PARAMS:
        if enum in gpu_params:
            result[enum] = gpu_params[enum]

    return result


def get_extensions(renderer_string: str, webgl_version: int = 1) -> list:
    """
    Get WebGL extensions list for a GPU.

    Args:
        renderer_string: ANGLE renderer string
        webgl_version: 1 or 2

    Returns:
        list: Extension names
    """
    if webgl_version == 1:
        return list(WEBGL1_EXTENSIONS_COMMON)

    r = renderer_string.upper()
    if "NVIDIA" in r:
        return sorted(WEBGL2_EXTENSIONS_NVIDIA)
    elif "AMD" in r or "RADEON" in r:
        return sorted(WEBGL2_EXTENSIONS_AMD)
    else:
        return sorted(WEBGL2_EXTENSIONS_INTEL)
