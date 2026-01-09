// Global type declaration to ensure JSX namespace is available
import React from 'react';

// Declare JSX namespace globally to fix react-markdown type issues
declare global {
  namespace JSX {
    interface IntrinsicElements extends React.JSX.IntrinsicElements {}
    interface IntrinsicAttributes extends React.JSX.IntrinsicAttributes {}
    type ElementType<P = any> = React.JSX.ElementType<P>;
  }
}

// Module declaration to fix react-markdown complex types
declare module 'react-markdown/lib/complex-types' {
  import { ComponentType } from 'react';
  import { ComponentPropsWithoutRef } from 'react';

  export type ReactMarkdownProps = {
    // Define any additional props you need for react-markdown
    [key: string]: any;
  };

  export type NormalComponents = {
    [TagName in keyof React.JSX.IntrinsicElements]?:
      | keyof React.JSX.IntrinsicElements
      | ComponentType<ComponentPropsWithoutRef<TagName> & ReactMarkdownProps>
  };
}

export {};