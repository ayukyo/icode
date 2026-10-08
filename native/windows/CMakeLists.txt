cmake_minimum_required(VERSION 3.20)
project(icode_windows_helpers C)

if(NOT WIN32)
  message(FATAL_ERROR "The native Windows helpers are Windows-only")
endif()

# The production baseline begins with a non-executing bootstrap. Never expose
# setup/command entry points until provenance and isolation gates are satisfied.
if(CMAKE_GENERATOR_PLATFORM STREQUAL "ARM64")
  set(ICODE_WINDOWS_ARCH arm64)
elseif(CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
  set(ICODE_WINDOWS_ARCH x64)
elseif(CMAKE_GENERATOR_PLATFORM STREQUAL "")
  string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" ICODE_WINDOWS_PROCESSOR)
  if(ICODE_WINDOWS_PROCESSOR MATCHES "^(arm64|aarch64)$")
    set(ICODE_WINDOWS_ARCH arm64)
  elseif(ICODE_WINDOWS_PROCESSOR MATCHES "^(amd64|x86_64)$")
    set(ICODE_WINDOWS_ARCH x64)
  endif()
endif()
option(ICODE_BUILD_WINDOWS_BOOTSTRAP "Build the verifier-bound bootstrap" ON)
set(ICODE_WINDOWS_PROVENANCE_VERIFIER "" CACHE FILEPATH "Actual architecture-matched Go verifier bytes")
if(ICODE_BUILD_WINDOWS_BOOTSTRAP)
  if(NOT DEFINED ICODE_WINDOWS_ARCH)
    message(FATAL_ERROR "Unsupported bootstrap architecture")
  endif()
  if(NOT IS_ABSOLUTE "${ICODE_WINDOWS_PROVENANCE_VERIFIER}" OR
     NOT EXISTS "${ICODE_WINDOWS_PROVENANCE_VERIFIER}")
    message(FATAL_ERROR "Bootstrap requires an explicit existing Go verifier")
  endif()
  find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
  set(ICODE_BINDING_HEADER "${CMAKE_CURRENT_BINARY_DIR}/icode_windows_verifier_binding.h")
  # A phony target runs on every build, including unchanged size/mtime inputs.
  # Nonzero generation blocks compilation and signing even with an old EXE.
  add_custom_target(icode_windows_bootstrap_binding
    COMMAND "${Python3_EXECUTABLE}" -B
      "${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/windows_bootstrap_binding.py"
      --verifier "${ICODE_WINDOWS_PROVENANCE_VERIFIER}"
      --architecture "${ICODE_WINDOWS_ARCH}" --output "${ICODE_BINDING_HEADER}"
    BYPRODUCTS "${ICODE_BINDING_HEADER}"
    VERBATIM
  )
  add_executable(icode_windows_bootstrap icode_windows_bootstrap.c)
  add_dependencies(icode_windows_bootstrap icode_windows_bootstrap_binding)
  target_include_directories(icode_windows_bootstrap PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  set_property(SOURCE icode_windows_bootstrap.c APPEND PROPERTY
    OBJECT_DEPENDS "${ICODE_BINDING_HEADER}")
  set_target_properties(icode_windows_bootstrap PROPERTIES
    OUTPUT_NAME "icode-sandbox-windows-${ICODE_WINDOWS_ARCH}"
    C_STANDARD 11
    C_STANDARD_REQUIRED YES
    C_EXTENSIONS NO
  )
endif()

add_executable(icode_appcontainer_read_probe icode_appcontainer_read_probe.c)
set_target_properties(icode_appcontainer_read_probe PROPERTIES
  OUTPUT_NAME "icode-appcontainer-read-probe"
  C_STANDARD 11
  C_STANDARD_REQUIRED YES
  C_EXTENSIONS NO
)
target_compile_definitions(icode_appcontainer_read_probe PRIVATE
  UNICODE
  _UNICODE
  _WIN32_WINNT=0x0A00
)
target_link_libraries(icode_appcontainer_read_probe PRIVATE iphlpapi ws2_32)

add_executable(icode_wfp_event_probe icode_wfp_event_probe.c)
set_target_properties(icode_wfp_event_probe PROPERTIES
  OUTPUT_NAME "icode-wfp-event-probe"
  C_STANDARD 11
  C_STANDARD_REQUIRED YES
  C_EXTENSIONS NO
)
target_compile_definitions(icode_wfp_event_probe PRIVATE
  UNICODE
  _UNICODE
  _WIN32_WINNT=0x0A00
)
target_link_libraries(icode_wfp_event_probe PRIVATE advapi32 fwpuclnt userenv ws2_32)

if(MSVC)
  if(TARGET icode_windows_bootstrap)
    set_property(TARGET icode_windows_bootstrap PROPERTY
      MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
    )
    target_compile_options(icode_windows_bootstrap PRIVATE /W4 /WX)
  endif()
  set_property(TARGET icode_appcontainer_read_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  set_property(TARGET icode_wfp_event_probe PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
  )
  target_compile_options(icode_appcontainer_read_probe PRIVATE /W4)
  target_compile_options(icode_wfp_event_probe PRIVATE /W4)
endif()

# CI-only selected build context; not product executable authorization.
option(ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC "Emit selected CI build metadata" OFF)
if(ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC)
  if(NOT ICODE_BUILD_WINDOWS_BOOTSTRAP OR NOT MSVC OR
     NOT CMAKE_GENERATOR MATCHES "^Visual Studio [0-9]+ [0-9][0-9][0-9][0-9]$" OR
     NOT CMAKE_GENERATOR_PLATFORM MATCHES "^(x64|ARM64)$")
    message(FATAL_ERROR "Build context diagnostic requires the selected VS bootstrap")
  endif()
  if(NOT IS_ABSOLUTE "${CMAKE_VS_MSBUILD_COMMAND}" OR
     NOT EXISTS "${CMAKE_VS_MSBUILD_COMMAND}" OR
     IS_DIRECTORY "${CMAKE_VS_MSBUILD_COMMAND}")
    message(FATAL_ERROR "Build context diagnostic requires an explicit existing MSBuild file")
  endif()
  # C0/DEL and UTF-8 C1 control characters match the Python receipt contract.
  # NUL cannot be represented in CMake strings; ordinary Unicode stays intact.
  set(_icode_context_json "{\"schema_version\":1")
  foreach(_icode_field IN ITEMS generator platform toolset sdk_version msbuild)
    if(_icode_field STREQUAL "generator")
      set(_icode_value "${CMAKE_GENERATOR}")
    elseif(_icode_field STREQUAL "platform")
      set(_icode_value "${CMAKE_GENERATOR_PLATFORM}")
    elseif(_icode_field STREQUAL "toolset")
      set(_icode_value "${CMAKE_VS_PLATFORM_TOOLSET}")
    elseif(_icode_field STREQUAL "sdk_version")
      set(_icode_value "${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}")
    else()
      set(_icode_value "${CMAKE_VS_MSBUILD_COMMAND}")
    endif()
    if(_icode_value STREQUAL "")
      message(FATAL_ERROR "Build context diagnostic requires nonempty selected values")
    endif()
    foreach(_icode_code RANGE 1 31)
      string(ASCII ${_icode_code} _icode_control)
      string(FIND "${_icode_value}" "${_icode_control}" _icode_position)
      if(NOT _icode_position EQUAL -1)
        message(FATAL_ERROR "Build context diagnostic rejects control characters")
      endif()
    endforeach()
    string(ASCII 127 _icode_control)
    string(FIND "${_icode_value}" "${_icode_control}" _icode_position)
    if(NOT _icode_position EQUAL -1)
      message(FATAL_ERROR "Build context diagnostic rejects control characters")
    endif()
    foreach(_icode_code RANGE 128 159)
      string(ASCII 194 ${_icode_code} _icode_control)
      string(FIND "${_icode_value}" "${_icode_control}" _icode_position)
      if(NOT _icode_position EQUAL -1)
        message(FATAL_ERROR "Build context diagnostic rejects control characters")
      endif()
    endforeach()
    string(REPLACE "\\" "\\\\" _icode_value "${_icode_value}")
    string(REPLACE "\"" "\\\"" _icode_value "${_icode_value}")
    string(APPEND _icode_context_json ",\"${_icode_field}\":\"${_icode_value}\"")
  endforeach()
  string(APPEND _icode_context_json "}\n")
  file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/icode-windows-build-context.json"
    CONTENT "${_icode_context_json}")
endif()
